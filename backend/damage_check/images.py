"""Image validation and (optional) downscaling. Pillow is optional: without it
we still sniff the file type and enforce the size limit."""
import io
from typing import Optional, Tuple

from .exceptions import InvalidInput

try:  # optional dependency
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageOps = None  # type: ignore


def sniff_mime(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(data: bytes, max_bytes: int) -> str:
    if not data:
        raise InvalidInput("Empty file.")
    if len(data) > max_bytes:
        raise InvalidInput("Image is too large (limit %d MB)." % (max_bytes // (1024 * 1024)))
    mime = sniff_mime(data)
    if mime is None:
        raise InvalidInput("Unsupported image type. Use JPEG, PNG or WebP.")
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except Exception:
            raise InvalidInput("File is not a readable image.")
    return mime


def prepare_for_model(data: bytes, mime: str, max_side: int) -> Tuple[bytes, str]:
    """Fix orientation and shrink so uploads to the model are fast and cheap."""
    if Image is None:
        return data, mime
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=85)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return data, mime
