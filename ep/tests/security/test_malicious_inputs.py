import io

import pytest
from PIL import Image

from ep_engine.core.exceptions import EPError
from ep_engine.services.images import decode_image


def test_animated_png_and_decompression_bomb(settings, image_bytes, monkeypatch):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        buffer, format="PNG", save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")]
    )
    with pytest.raises(EPError) as caught:
        decode_image(buffer.getvalue(), None, settings)
    assert caught.value.code == "animated_image"
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 300)
    with pytest.raises(EPError) as caught:
        decode_image(image_bytes(), None, settings)
    assert caught.value.status == 413


def test_raw_and_chunked_body_limits(client, application, settings, auth, image_bytes, headers):
    from fastapi.testclient import TestClient

    from ep_engine.main import create_app

    small = settings.model_copy(update={"max_upload_bytes": 200})
    with TestClient(create_app(small, authorization=auth)) as limited:
        for body in (b"x" * 201, iter([b"x" * 100, b"x" * 101])):
            result = limited.post(
                "/v1/evidence?rental_id=rental-1&stage=before", content=body, headers=headers
            )
            assert result.status_code == 413
            assert result.json()["error"]["code"] == "body_limit"
        assert (
            limited.post("/v1/inspections", content=b" " * 201, headers=headers).status_code == 413
        )


def test_missing_unknown_images_and_declared_content(client, headers, image_bytes):
    url = "/v1/evidence?rental_id=rental-1&stage=before"
    for data, mime, status in (
        (b"", "image/png", 422),
        (b"<svg onload='bad()'/>", "image/png", 422),
        (image_bytes(), "image/jpeg", 415),
        (image_bytes("JPEG"), "image/jpeg", 201),
    ):
        result = client.post(url, content=data, headers={**headers, "Content-Type": mime})
        assert result.status_code == status
    assert (
        client.get("/v1/evidence/00000000-0000-0000-0000-000000000000", headers=headers).status_code
        == 404
    )
    assert (
        client.get(
            "/v1/inspections/00000000-0000-0000-0000-000000000000", headers=headers
        ).status_code
        == 404
    )


def test_query_json_injection_and_forbidden_fields(client, headers, evidence_pair):
    assert (
        client.post(
            "/v1/evidence?rental_id=../../backend&stage=before", content=b"x", headers=headers
        ).status_code
        == 422
    )
    evidence_pair["status"] = "completed"
    assert client.post("/v1/inspections", headers=headers, json=evidence_pair).status_code == 422
    assert client.post("/v1/inspections", headers=headers, content=b"{invalid").status_code == 422


def test_allowed_borrower_read_and_configured_cors(client, upload, auth, settings):
    from fastapi.testclient import TestClient

    from ep_engine.main import create_app

    record = upload().json()
    assert (
        client.get(
            f"/v1/evidence/{record['id']}/content",
            headers={"Authorization": "Bearer test-borrower-token"},
        ).status_code
        == 200
    )
    allowed = "http://127.0.0.1:5173"
    with TestClient(
        create_app(settings.model_copy(update={"cors_origins": (allowed,)}), authorization=auth)
    ) as browser:
        result = browser.options(
            "/v1/evidence", headers={"Origin": allowed, "Access-Control-Request-Method": "POST"}
        )
        assert result.headers["access-control-allow-origin"] == allowed
