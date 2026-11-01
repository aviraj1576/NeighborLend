import os
import uuid
import shutil
from pathlib import Path
from fastapi import UploadFile, HTTPException
from app.config import get_settings
from supabase import create_client, Client

settings = get_settings()

supabase: Client = None
_public_bucket_ready = False
if settings.supabase_url and settings.supabase_service_role_key:
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)


def _ensure_public_bucket(bucket_name: str) -> None:
    """Create the bucket when absent and make existing buckets browser-readable."""
    global _public_bucket_ready
    if _public_bucket_ready:
        return
    try:
        supabase.storage.create_bucket(bucket_name, options={"public": True})
    except Exception:
        # Supabase also raises when the bucket already exists. Update it instead
        # of assuming that an existing bucket is public.
        try:
            supabase.storage.update_bucket(bucket_name, options={"public": True})
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Could not configure Supabase bucket '{bucket_name}': {exc}",
            ) from exc
    _public_bucket_ready = True


def _make_filename(original_filename: str) -> str:
    suffix = Path(original_filename or "").suffix.lower()
    return f"{uuid.uuid4()}{suffix}"

def save_upload(file: UploadFile, subfolder: str = "") -> str:
    filename = _make_filename(file.filename)
    
    if supabase:
        bucket_name = "listing-images"
        path_in_bucket = f"{subfolder}/{filename}" if subfolder else filename
        file_bytes = file.file.read()
        try:
            _ensure_public_bucket(bucket_name)
            supabase.storage.from_(bucket_name).upload(
                path_in_bucket,
                file_bytes,
                file_options={"content-type": file.content_type or "application/octet-stream"},
            )
            return supabase.storage.from_(bucket_name).get_public_url(path_in_bucket)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error uploading to Supabase: {str(e)}")
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
    subfolder: str = ""
) -> str:
    filename = _make_filename(original_filename)

    if supabase:
        bucket_name = "listing-images"
        path_in_bucket = f"{subfolder}/{filename}" if subfolder else filename

        try:
            _ensure_public_bucket(bucket_name)

            supabase.storage.from_(bucket_name).upload(
                path_in_bucket,
                file_bytes,
                file_options={"content-type": content_type or "application/octet-stream"}
            )

            return supabase.storage.from_(
                bucket_name
            ).get_public_url(path_in_bucket)

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error uploading to Supabase: {str(e)}"
            )

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
        bucket_name = "listing-images"
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
