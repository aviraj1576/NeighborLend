"""Uploads must use the same trained class IDs and filtering as identification."""

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.routers import uploads
from app.services import ai_identifier, ml_service


@pytest.fixture
def rental_model(monkeypatch):
    names = dict(enumerate((
        "electric_drill", "screwdriver", "wrench", "hammer", "smartphone", "laptop",
        "camera", "headphones", "keyboard", "drone", "bicycle", "scooter", "tent",
        "umbrella", "basketball", "dumbbell", "barbell", "microwave", "kettle",
        "blender", "backpack", "camping_chair", "suitcase", "guitar",
    )))
    model = SimpleNamespace(names=names, predict=Mock())
    # The trained checkpoint's kettle ID is 18; excluding ID 15 must not shift it.
    boxes = []
    for class_id, confidence in ((15, 0.99), (18, 0.91), (7, 0.5)):
        box = Mock()
        box.cls.item.return_value = class_id
        box.conf.item.return_value = confidence
        boxes.append(box)
    model.predict.return_value = [SimpleNamespace(boxes=boxes)]
    monkeypatch.setattr(ai_identifier, "_model", model)
    monkeypatch.setattr(ai_identifier, "YOLO_AVAILABLE", True)
    monkeypatch.setattr(ai_identifier.settings, "ai_confidence_threshold", 0.45)
    return model


@pytest.fixture
def image_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_upload_uses_original_class_ids_and_excludes_dumbbell(rental_model, image_bytes):
    detections = ml_service.detect_objects(image_bytes)
    assert detections == [
        {"class": "Kettle", "confidence": 0.91},
        {"class": "Headphones", "confidence": 0.5},
    ]
    options = rental_model.predict.call_args.kwargs
    assert len(options["classes"]) == 23
    assert 15 not in options["classes"]
    assert 18 in options["classes"]
    assert options["imgsz"] == 640
    assert options["conf"] == 0.45


def test_upload_returns_model_result_to_listing_screen(monkeypatch, rental_model, image_bytes):
    save_upload = Mock(return_value="https://project.supabase.co/storage/v1/object/public/listing_photos/images/kettle.png")
    monkeypatch.setattr(uploads, "save_upload_from_bytes", save_upload)
    upload = UploadFile(
        file=io.BytesIO(image_bytes), filename="item.png",
        headers=Headers({"content-type": "image/png"}),
    )
    response = asyncio.run(uploads.upload_file(file=upload, current_user=SimpleNamespace()))
    assert response["url"].startswith("https://project.supabase.co/storage/v1/object/public/listing_photos/")
    assert save_upload.call_args.kwargs["require_supabase"] is True
    assert response["ai_label"] == "Kettle"
    assert response["ai_confidence"] == 0.91
    assert len(response["detections"]) == 2


def test_upload_respects_configured_confidence(monkeypatch, rental_model, image_bytes):
    monkeypatch.setattr(ai_identifier.settings, "ai_confidence_threshold", 0.8)
    assert ml_service.detect_objects(image_bytes) == [{"class": "Kettle", "confidence": 0.91}]
    assert rental_model.predict.call_args.kwargs["conf"] == 0.8


@pytest.mark.parametrize("threshold,accepted", [(0.25, True), (0.45, False)])
def test_barbell_at_25_percent_respects_threshold(
    monkeypatch, rental_model, image_bytes, threshold, accepted
):
    monkeypatch.setattr(ai_identifier.settings, "ai_confidence_threshold", threshold)
    box = Mock()
    box.cls.item.return_value = 16
    box.conf.item.return_value = 0.2501809895038605
    rental_model.predict.return_value = [SimpleNamespace(boxes=[box])]
    expected = [{"class": "Barbell", "confidence": 0.2502}] if accepted else []
    assert ml_service.detect_objects(image_bytes) == expected
    assert rental_model.predict.call_args.kwargs["conf"] == threshold


def test_startup_warms_shared_model(rental_model):
    from app.main import _preload_model

    _preload_model()
    assert ai_identifier._get_model() is rental_model
    rental_model.predict.assert_called_once()
    assert rental_model.predict.call_args.kwargs["classes"] == ai_identifier.get_allowed_classes(
        rental_model
    )


def test_loader_reuses_one_yoloe_instance(monkeypatch, rental_model, tmp_path):
    checkpoint = tmp_path / "rental.pt"
    checkpoint.write_bytes(b"test checkpoint")
    monkeypatch.setattr(ai_identifier.settings, "ai_model_path", str(checkpoint))
    monkeypatch.setattr(ai_identifier, "_model", None)
    loader = Mock(return_value=rental_model)
    monkeypatch.setattr(ai_identifier, "YOLOE", loader)
    assert ai_identifier._get_model() is rental_model
    assert ai_identifier._get_model() is rental_model
    loader.assert_called_once_with(str(checkpoint))


def test_loader_rejects_old_nine_class_model(monkeypatch, rental_model, tmp_path, caplog):
    checkpoint = tmp_path / "old.pt"
    checkpoint.write_bytes(b"test checkpoint")
    monkeypatch.setattr(ai_identifier.settings, "ai_model_path", str(checkpoint))
    monkeypatch.setattr(ai_identifier, "_model", None)
    monkeypatch.setattr(ai_identifier, "YOLOE", Mock(return_value=SimpleNamespace(
        names=dict(enumerate(("bicycle", "book", "drill", "hammer", "headphones",
                              "ladder", "keyboard", "pliers", "umbrella"))),
    )))
    assert ai_identifier._get_model() is None
    assert "Expected 23 active rental classes, got 9" in caplog.text


def test_photo_upload_survives_missing_model(monkeypatch, rental_model, image_bytes):
    monkeypatch.setattr(ai_identifier, "_get_model", lambda: None)
    assert ml_service.detect_objects(image_bytes) == []


def test_invalid_image_has_no_predictions(rental_model):
    assert ml_service.detect_objects(b"not an image") == []
    rental_model.predict.assert_not_called()
