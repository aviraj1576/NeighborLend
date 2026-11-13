"""Private, content-identified evidence for the existing rental workflow."""

import hashlib
import io
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.config import BACKEND_DIR, get_settings
from app.payment_models import RentalEvidence

PREFIX = "/api/payments/evidence/"


def evidence_directory():
    settings = get_settings()
    directory = Path(settings.rental_evidence_dir)
    directory = (directory if directory.is_absolute() else BACKEND_DIR / directory).resolve()
    if directory.is_relative_to(Path(settings.upload_dir_abs).resolve()):
        raise HTTPException(503, "Rental evidence must be stored outside public uploads")
    return directory


def save_evidence(db, booking, actor, stage, data):
    if stage not in {"handover", "receipt", "return"}:
        raise HTTPException(422, "Invalid evidence stage")
    expected_actor = booking.lender_id if stage == "handover" else booking.borrower_id
    if actor != expected_actor:
        raise HTTPException(403, "Not authorized for this evidence stage")
    if booking.payment_status != "captured" or booking.settlement_kind:
        raise HTTPException(409, "Evidence requires an unsettled funded booking")
    from app.models import BorrowRequest

    request = db.get(BorrowRequest, booking.borrow_request_id)
    eligible = {
        "handover": {"pending", "photos_uploaded"},
        "receipt": {"photos_uploaded"},
        "return": {"lender_confirmed"},
    }
    if request.handover_status not in eligible[stage]:
        raise HTTPException(409, "Rental is not eligible for this evidence stage")
    if not data or len(data) > 8_000_000:
        raise HTTPException(413, "Evidence must be between 1 byte and 8 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG"} or image.width * image.height > 20_000_000:
                raise ValueError("Unsupported image")
            media_type = "image/jpeg" if image.format == "JPEG" else "image/png"
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "A valid bounded JPEG or PNG is required") from None
    identity = str(uuid4())
    directory = evidence_directory()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (identity + ".image")
    with target.open("xb") as stream:
        stream.write(data)
    record = RentalEvidence(
        id=identity,
        booking_id=booking.id,
        uploaded_by=actor,
        stage=stage,
        storage_name=target.name,
        sha256=hashlib.sha256(data).hexdigest(),
        media_type=media_type,
    )
    db.add(record)
    return record, target


def validate_references(db, booking, actor, stage, references):
    if len(set(references)) != len(references):
        raise HTTPException(422, "Duplicate evidence references")
    for reference in references:
        try:
            if not reference.startswith(PREFIX):
                raise ValueError()
            identity = str(UUID(reference[len(PREFIX) :]))
        except (ValueError, TypeError):
            raise HTTPException(422, "Use private rental evidence uploads") from None
        row = db.get(RentalEvidence, identity)
        if not row or (row.booking_id, row.uploaded_by, row.stage) != (booking.id, actor, stage):
            raise HTTPException(403, "Evidence does not belong to this rental, user and stage")


def read_evidence(row):
    # Storage names are generated UUIDs, never client paths.
    if row.storage_name != row.id + ".image":
        raise HTTPException(409, "Evidence integrity check failed")
    try:
        data = (evidence_directory() / row.storage_name).read_bytes()
    except OSError:
        raise HTTPException(404, "Evidence content unavailable") from None
    if hashlib.sha256(data).hexdigest() != row.sha256:
        raise HTTPException(409, "Evidence integrity check failed")
    return data
