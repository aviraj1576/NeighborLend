import os
import uuid
import shutil
import base64
import json
import logging
import re
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from fastapi import UploadFile, HTTPException
from app.config import get_settings
from supabase import create_client, Client

settings = get_settings()
logger = logging.getLogger(__name__)
LISTING_PHOTOS_BUCKET = "listing_photos"

supabase: Client = None
_public_bucket_ready = False
if settings.supabase_url and settings.supabase_service_role_key:
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)


def _project_binding_status() -> str:
    """Compare a legacy Supabase JWT's project ref without exposing the key."""
    try:
        host = urlsplit(settings.supabase_url).hostname or ""
    except ValueError:
        return "unverifiable"
    suffix = ".supabase.co"
    if not host.endswith(suffix):
        return "unverifiable"

    parts = settings.supabase_service_role_key.split(".")
    if len(parts) != 3:
        return "unverifiable"
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return "unverifiable"
    key_ref = claims.get("ref") if isinstance(claims, dict) else None
    if not isinstance(key_ref, str) or not key_ref:
        return "unverifiable"
    return "match" if host[: -len(suffix)].lower() == key_ref.lower() else "mismatch"


def _safe_diagnostic_value(value) -> str:
    """Remove credentials and URL query data before writing exception details to logs."""
    message = str(value or "")
    configured_key = settings.supabase_service_role_key
    if configured_key:
        message = message.replace(configured_key, "[REDACTED]")
    message = re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        "[REDACTED_JWT]",
        message,
    )
    message = re.sub(r"\bsb_secret_[A-Za-z0-9_-]+\b", "[REDACTED_SECRET_KEY]", message)
    message = re.sub(r"(?i)\bbearer\s+[^\s,;'\"]+", "Bearer [REDACTED]", message)
    message = re.sub(
        r"(?i)(api[_ -]?key|authorization|service[_ -]?role[_ -]?key|access[_ -]?token|refresh[_ -]?token|secret)(\s*[:=]\s*)[^\s,;'\"]+",
        r"\1\2[REDACTED]",
        message,
    )
    message = re.sub(
        r"https?://[^\s'\"<>]+",
        lambda match: _safe_url_for_log(match.group(0)),
        message,
    )
    return message[:500]


def _safe_url_for_log(value: str) -> str:
    try:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.hostname or "[invalid-host]", parsed.path, "", ""))
    except ValueError:
        return "[REDACTED_URL]"


def _log_bucket_lookup_failure(exc: Exception) -> None:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
    message = getattr(exc, "message", None) or str(exc)
    logger.error(
        "Supabase Storage bucket lookup failed: exception_class=%s http_status=%s "
        "error_code=%s project_binding=%s safe_message=%s",
        type(exc).__name__,
        _safe_diagnostic_value(status if status is not None else "unavailable"),
        _safe_diagnostic_value(code if code is not None else "unavailable"),
        _project_binding_status(),
        _safe_diagnostic_value(message),
    )


def _ensure_public_bucket(bucket_name: str = LISTING_PHOTOS_BUCKET) -> None:
    """Check the configured existing bucket; never create or change bucket settings."""
    global _public_bucket_ready
    if _public_bucket_ready:
        return
    if bucket_name != LISTING_PHOTOS_BUCKET:
        raise HTTPException(status_code=500, detail="Unexpected listing photo bucket configuration.")
    project_binding = _project_binding_status()
    if project_binding == "mismatch":
        logger.error(
            "Supabase Storage bucket lookup skipped: exception_class=ProjectBindingMismatch "
            "http_status=not_applicable error_code=not_applicable project_binding=mismatch "
            "safe_message=SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY belong to different projects"
        )
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must belong to the same Supabase project.",
        )
    try:
        bucket = supabase.storage.get_bucket(bucket_name)
    except Exception as exc:
        _log_bucket_lookup_failure(exc)
        raise HTTPException(
            status_code=503,
            detail=f"The existing Supabase Storage bucket '{bucket_name}' was not found or could not be checked.",
        ) from exc
    is_public = bucket.get("public") if isinstance(bucket, dict) else getattr(bucket, "public", None)
    if is_public is not True:
        raise HTTPException(
            status_code=503,
            detail=f"Make the existing Supabase Storage bucket '{bucket_name}' public to display listing photos.",
        )
    _public_bucket_ready = True


def _make_filename(original_filename: str) -> str:
    suffix = Path(original_filename or "").suffix.lower()
    return f"{uuid.uuid4()}{suffix}"


def is_public_listing_image_url(url: str) -> bool:
    """Return true only for public URLs in this app's configured Supabase bucket."""
    if not settings.supabase_url or not isinstance(url, str):
        return False
    try:
        expected = urlsplit(settings.supabase_url)
        actual = urlsplit(url)
        return (
            expected.scheme == "https"
            and actual.scheme == "https"
            and actual.hostname == expected.hostname
            and actual.username is None
            and actual.password is None
            and actual.port in (None, 443)
            and not actual.query
            and not actual.fragment
            and actual.path.startswith(f"/storage/v1/object/public/{LISTING_PHOTOS_BUCKET}/")
            and len(actual.path) > len(f"/storage/v1/object/public/{LISTING_PHOTOS_BUCKET}/")
        )
    except ValueError:
        return False


def _require_supabase_storage() -> None:
    if supabase is None:
        raise HTTPException(
            status_code=503,
            detail="Listing photo uploads require SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on the backend.",
        )


def _upload_to_supabase(file_bytes: bytes, object_path: str, content_type: str) -> str:
    _require_supabase_storage()
    try:
        _ensure_public_bucket()
        supabase.storage.from_(LISTING_PHOTOS_BUCKET).upload(
            object_path,
            file_bytes,
            file_options={"content-type": content_type or "application/octet-stream", "upsert": "true"},
        )
        public_url = supabase.storage.from_(LISTING_PHOTOS_BUCKET).get_public_url(object_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not upload the image to Supabase Storage.") from exc

    if not is_public_listing_image_url(public_url):
        raise HTTPException(status_code=502, detail="Supabase returned an invalid public image URL.")
    return public_url

def save_upload(file: UploadFile, subfolder: str = "") -> str:
    filename = _make_filename(file.filename)
    
    if supabase:
        file_bytes = file.file.read()
        path_in_bucket = f"{subfolder}/{filename}" if subfolder else filename
        return _upload_to_supabase(file_bytes, path_in_bucket, file.content_type or "application/octet-stream")
    else:
        upload_dir = os.path.join(settings.upload_dir_abs, subfolder)
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        url_path = f"/uploads/{subfolder}/{filename}" if subfolder else f"/uploads/{filename}"
        url_path = url_path.replace("//", "/")
        return f"{settings.public_base_url}{url_path}"
    
    
def save_upload_from_bytes(
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    subfolder: str = "",
    *,
    require_supabase: bool = False,
    object_path: str = None,
) -> str:
    filename = _make_filename(original_filename)

    if supabase or require_supabase or object_path:
        path_in_bucket = object_path or (f"{subfolder}/{filename}" if subfolder else filename)
        return _upload_to_supabase(file_bytes, path_in_bucket, content_type or "application/octet-stream")
    else:
        upload_dir = os.path.join(settings.upload_dir_abs, subfolder)
        os.makedirs(upload_dir, exist_ok=True)

        filepath = os.path.join(upload_dir, filename)

        with open(filepath, "wb") as buffer:
            buffer.write(file_bytes)

        url_path = (
            f"/uploads/{subfolder}/{filename}"
            if subfolder
            else f"/uploads/{filename}"
        )

        return f"{settings.public_base_url}{url_path}"

def delete_upload(url: str):
    if supabase and url.startswith(settings.supabase_url):
        bucket_name = LISTING_PHOTOS_BUCKET
        try:
            parts = url.split(f"/object/public/{bucket_name}/")
            if len(parts) == 2:
                path_in_bucket = parts[1]
                supabase.storage.from_(bucket_name).remove([path_in_bucket])
        except Exception:
            pass
        return

    if settings.public_base_url:
        if not url.startswith(settings.public_base_url):
            return
        path_part = url[len(settings.public_base_url):]
    else:
        path_part = url

    if not path_part.startswith("/uploads/"):
        return

    upload_root = os.path.abspath(settings.upload_dir_abs)
    filepath = os.path.abspath(
        os.path.join(upload_root, path_part.removeprefix("/uploads/"))
    )
    if os.path.commonpath((upload_root, filepath)) != upload_root:
        return
    if os.path.isfile(filepath):
        os.remove(filepath)
