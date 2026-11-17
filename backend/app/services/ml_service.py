from app.services.ai_identifier import identify_item


def detect_objects(image_bytes: bytes):
    """Keep the upload response format while sharing the 23-class identifier."""
    return [
        {"class": prediction["label"], "confidence": round(prediction["confidence"], 4)}
        for prediction in identify_item(image_bytes)["predictions"]
    ]
