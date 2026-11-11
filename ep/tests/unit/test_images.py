import hashlib
import io

import pytest
from PIL import Image

from ep_engine.core.exceptions import EPError
from ep_engine.services.images import decode_image


@pytest.mark.parametrize("fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png")])
def test_real_decoding_preserves_integrity(settings, image_bytes, fmt, mime):
    original = image_bytes(fmt)
    result = decode_image(original, mime, settings)
    assert result.sha256 == hashlib.sha256(original).hexdigest()
    assert result.content_type == mime
    assert (result.width, result.height) == (24, 16)
    with Image.open(io.BytesIO(result.normalized)) as decoded:
        assert decoded.size == (24, 16)
        assert not decoded.getexif()


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\nmalicious"])
def test_bad_images(settings, data):
    with pytest.raises(EPError):
        decode_image(data, None, settings)


def test_mime_and_limits(settings, image_bytes):
    data = image_bytes()
    for mime, options, status in [
        ("image/jpeg", {}, 415),
        ("application/octet-stream", {}, 415),
        (None, {"max_upload_bytes": len(data) - 1}, 413),
        (None, {"max_pixels": 383}, 413),
        (None, {"max_dimension": 23}, 413),
    ]:
        with pytest.raises(EPError) as caught:
            decode_image(data, mime, settings.model_copy(update=options))
        assert caught.value.status == status


def test_orientation_is_derivative_only(settings, image_bytes):
    exif = Image.Exif()
    exif[274] = 6
    original = image_bytes("JPEG", exif=exif)
    result = decode_image(original, None, settings)
    assert (result.width, result.height) == (16, 24)
    assert result.sha256 == hashlib.sha256(original).hexdigest()


def test_truncated_and_other_formats(settings, image_bytes):
    for data in (image_bytes("JPEG")[:100], image_bytes("GIF")):
        with pytest.raises(EPError):
            decode_image(data, None, settings)


def test_exact_byte_pixel_dimension_limits_are_accepted(settings, image_bytes):
    data = image_bytes()
    limits = settings.model_copy(
        update={"max_upload_bytes": len(data), "max_pixels": 384, "max_dimension": 24}
    )
    assert decode_image(data, "image/png", limits).sha256


def test_corrupt_png_checksum_is_rejected(settings, image_bytes):
    data = bytearray(image_bytes())
    data[45] ^= 255
    with pytest.raises(EPError):
        decode_image(bytes(data), None, settings)
