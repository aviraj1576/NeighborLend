import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from ep_engine.config import Settings
from ep_engine.core.exceptions import EPError


@dataclass(frozen=True)
class DecodedImage:
    sha256: str
    normalized_sha256: str
    content_type: str
    width: int
    height: int
    normalized: bytes


def decode_image(data: bytes, declared_mime: str | None, settings: Settings) -> DecodedImage:
    if not data:
        raise EPError(422, "empty_image", "Image body is empty")
    if len(data) > settings.max_upload_bytes:
        raise EPError(413, "image_limit", "Image exceeds byte limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=("JPEG", "PNG")) as image:
                mime = {"JPEG": "image/jpeg", "PNG": "image/png"}[image.format]
                if declared_mime and declared_mime.lower().split(";")[0].strip() != mime:
                    raise EPError(
                        415, "mime_mismatch", "Declared type does not match image content"
                    )
                if (
                    image.width * image.height > settings.max_pixels
                    or max(image.size) > settings.max_dimension
                ):
                    raise EPError(413, "image_limit", "Image exceeds pixel or dimension limit")
                if getattr(image, "n_frames", 1) != 1:
                    raise EPError(415, "animated_image", "Animated evidence is unsupported")
                image.verify()
            # verify checks the container; load decodes pixels and detects JPEG truncation.
            with Image.open(io.BytesIO(data), formats=("JPEG", "PNG")) as original:
                original.load()
                normalized = ImageOps.exif_transpose(original).convert("RGB")
                width, height = normalized.size
                # Strip EXIF/GPS/comments/ICC from the derivative; original bytes stay unchanged.
                clean = Image.new("RGB", normalized.size)
                clean.paste(normalized)
                output = io.BytesIO()
                clean.save(output, format="PNG")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise EPError(413, "image_limit", "Unsafe decoded image size") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise EPError(422, "invalid_image", "Invalid or corrupted JPEG/PNG") from exc
    derivative = output.getvalue()
    return DecodedImage(
        hashlib.sha256(data).hexdigest(),
        hashlib.sha256(derivative).hexdigest(),
        mime,
        width,
        height,
        derivative,
    )
