"""Compatibility adapter for listing uploads using the shared YOLOE classifier."""

from app.services.ai_identifier import identify_item


def detect_objects(image_bytes: bytes):
    # Keep /upload's existing response contract while sharing model loading,
    # configured confidence, class exclusions, and graceful inference fallback.
    result = identify_item(image_bytes)
    return [
        {"class": prediction["label"], "confidence": prediction["confidence"]}
        for prediction in result["predictions"]
    ]
