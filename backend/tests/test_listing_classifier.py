"""Listing upload and identification share YOLOE exclusions/fallbacks; no model loads."""
import io
from types import SimpleNamespace

import pytest
from PIL import Image
from test_razorpay_escrow import flow as payment_flow

from app.services import ai_identifier, ml_service

flow = payment_flow


def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(stream, format="PNG")
    return stream.getvalue()


def box(label, confidence):
    return SimpleNamespace(cls=SimpleNamespace(item=lambda: label),
                           conf=SimpleNamespace(item=lambda: confidence))


def test_upload_uses_identification_confidence_names_and_exclusions(flow, monkeypatch):
    calls = []

    class Model:
        names = {0: "dumb-bell", 1: "electric_drill", 2: "book"}

        def predict(self, **kwargs):
            calls.append(kwargs)
            return [SimpleNamespace(boxes=[box(0, .99), box(1, .9), box(2, .2)])]

    monkeypatch.setattr(ai_identifier, "_get_model", lambda: Model())
    monkeypatch.setattr(ai_identifier.settings, "ai_confidence_threshold", .73)
    monkeypatch.setattr("app.routers.uploads.save_upload_from_bytes", lambda *args, **kwargs: "/uploads/synthetic.png")
    identified = flow["client"].post("/api/ai/identify", files={"image": ("item.png", image_bytes(), "image/png")})
    uploaded = flow["client"].post("/api/upload", headers=flow["headers"]["borrower"], files={"file": ("item.png", image_bytes(), "image/png")})
    assert identified.status_code == uploaded.status_code == 200
    assert identified.json()["predictions"] == [{"label": "Drill", "confidence": .9}]
    assert uploaded.json() == {"url": "/uploads/synthetic.png", "ai_label": "Drill", "ai_confidence": .9,
                              "detections": [{"class": "Drill", "confidence": .9}]}
    assert len(calls) == 2
    assert all(call["classes"] == [1, 2] and call["conf"] == .73 for call in calls)


@pytest.mark.parametrize("mode", ["missing", "inference_failure", "no_predictions"])
def test_classifier_failures_leave_upload_available(flow, monkeypatch, mode):
    class Model:
        names = {0: "drill"}

        def predict(self, **kwargs):
            if mode == "inference_failure":
                raise RuntimeError("Synthetic inference failure")
            return []

    monkeypatch.setattr(ai_identifier, "_get_model", lambda: None if mode == "missing" else Model())
    monkeypatch.setattr("app.routers.uploads.save_upload_from_bytes", lambda *args, **kwargs: "/uploads/synthetic.png")
    response = flow["client"].post("/api/upload", headers=flow["headers"]["borrower"], files={"file": ("item.png", image_bytes(), "image/png")})
    assert response.status_code == 200
    assert response.json()["url"] == "/uploads/synthetic.png"
    assert response.json()["ai_label"] is None
    assert response.json()["detections"] == []


def test_excluded_classes_keep_their_original_ids():
    model = SimpleNamespace(names={2: "Dumb bells", 5: "electric_drill", 9: "dumbbells", 12: "book"})
    assert ai_identifier.get_allowed_classes(model) == [5, 12]


def test_preload_warms_the_shared_classifier(monkeypatch):
    from app.main import _preload_model

    images = []
    monkeypatch.setattr(ai_identifier, "identify_item", lambda data: images.append(data) or {"model_available": True})
    _preload_model()
    assert len(images) == 1
    with Image.open(io.BytesIO(images[0])) as image:
        assert image.size == (640, 640)


def test_upload_adapter_preserves_model_unavailable_fallback(monkeypatch):
    monkeypatch.setattr(ai_identifier, "_get_model", lambda: None)
    assert ml_service.detect_objects(image_bytes()) == []
