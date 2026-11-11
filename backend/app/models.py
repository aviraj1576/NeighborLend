import enum
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database import Base

def _uuid() -> str:
    return str(uuid.uuid4())

class ListingStatus(str, enum.Enum):
    draft = "draft"
    pending_review = "pending_review"
    published = "published"
    flagged = "flagged"
    paused = "paused"
    removed = "removed"

class BorrowRequestStatus(str, enum.Enum):
    open = "open"
    fulfilled = "fulfilled"
    closed = "closed"
    cancelled = "cancelled"

class HandoverStatus(str, enum.Enum):
    not_applicable = "not_applicable"
    pending = "pending"
    photos_uploaded = "photos_uploaded"          # Lender uploaded photos of item
    borrower_confirmed = "borrower_confirmed"    # Borrower marked as received (starts rental)
    lender_confirmed = "lender_confirmed"        # Lender confirmed handover complete
    issue_reported = "issue_reported"
    return_photos_uploaded = "return_photos_uploaded"  # Borrower uploaded return photos
    return_confirmed = "return_confirmed"        # Lender confirmed return

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    is_verified = Column(Boolean, nullable=False, default=True, server_default="true")
    google_sub = Column(String, unique=True, nullable=True, index=True)
    avatar_url = Column(String, nullable=True)
    trust_score = Column(Float, default=50.0)
    avg_rating = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    completed_rentals_count = Column(Integer, default=0)
    disputes_against_count = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    listings = relationship("Listing", back_populates="owner", foreign_keys="Listing.owner_id")
    borrow_requests = relationship("BorrowRequest", back_populates="borrower", foreign_keys="BorrowRequest.borrower_id")

class CaptchaChallenge(Base):
    __tablename__ = "captcha_challenges"
    id = Column(String, primary_key=True, default=_uuid)
    answer = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

class EmailVerification(Base):
    __tablename__ = "email_verifications"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_sent_at = Column(DateTime, nullable=False)

class Listing(Base):
    __tablename__ = "listings"
    id = Column(String, primary_key=True, default=_uuid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, default="")
    years_owned = Column(Float, default=0)
    price_bought = Column(Float, default=0)
    price_per_day = Column(Float, nullable=False)
    min_price_per_day = Column(Float, nullable=True)
    security_deposit = Column(Float, default=0)
    lending_radius_km = Column(Float, default=10)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address_text = Column(String, default="")
    status = Column(Enum(ListingStatus), default=ListingStatus.published, index=True)
    moderation_reason = Column(String, nullable=True)
    ai_label = Column(String, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner = relationship("User", back_populates="listings", foreign_keys=[owner_id])
    photos = relationship("ListingPhoto", back_populates="listing", cascade="all, delete-orphan")

class ListingPhoto(Base):
    __tablename__ = "listing_photos"
    id = Column(String, primary_key=True, default=_uuid)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False, index=True)
    url = Column(String, nullable=False)
    is_cover = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    listing = relationship("Listing", back_populates="photos")

class BorrowRequest(Base):
    __tablename__ = "borrow_requests"
    id = Column(String, primary_key=True, default=_uuid)
    borrower_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, default="")
    max_price_per_day = Column(Float, nullable=True)
    needed_from = Column(DateTime, nullable=True)
    needed_until = Column(DateTime, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    radius_km = Column(Float, default=10)
    address_text = Column(String, default="")
    status = Column(Enum(BorrowRequestStatus), default=BorrowRequestStatus.open, index=True)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=True)
    total_cost = Column(Float, nullable=True)
    handover_status = Column(String, nullable=False, default=HandoverStatus.not_applicable.value, server_default=HandoverStatus.not_applicable.value)
    handover_marked_at = Column(DateTime, nullable=True)
    handover_confirmed_at = Column(DateTime, nullable=True)
    handover_confirmed_by = Column(String, nullable=True)
    handover_issue_description = Column(Text, nullable=True)
    handover_issue_reported_at = Column(DateTime, nullable=True)
    handover_photos = Column(Text, nullable=True)           # JSON array of photo URLs (lender uploads)
    handover_confirmed_photos = Column(Text, nullable=True) # JSON array of photo URLs (borrower confirms)
    handover_condition_note = Column(Text, nullable=True)
    return_condition_note = Column(Text, nullable=True)
    return_photos = Column(Text, nullable=True)             # JSON array of photo URLs (borrower uploads on return)
    return_confirmed_at = Column(DateTime, nullable=True)
    return_confirmed_by = Column(String, nullable=True)
    borrowing_started_at = Column(DateTime, nullable=True)
    return_due_at = Column(DateTime, nullable=True)
    returned_at = Column(DateTime, nullable=True)
    disputed_at = Column(DateTime, nullable=True)
    dispute_description = Column(Text, nullable=True)
    lender_rating = Column(Integer, nullable=True)          # Rating given by borrower to lender (1-5)
    borrower_rating = Column(Integer, nullable=True)        # Rating given by lender to borrower (1-5)
    lender_rating_comment = Column(Text, nullable=True)
    borrower_rating_comment = Column(Text, nullable=True)
    lender_rated_at = Column(DateTime, nullable=True)
    borrower_rated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    borrower = relationship("User", back_populates="borrow_requests", foreign_keys=[borrower_id])
    listing = relationship("Listing", foreign_keys=[listing_id])
    negotiation_offers = relationship("NegotiationOffer", back_populates="borrow_request")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    notification_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    link_url = Column(String, nullable=False)
    borrow_request_id = Column(String, ForeignKey("borrow_requests.id"), nullable=True, index=True)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

class OfferStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    countered = "countered"
    cancelled = "cancelled"

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, default=_uuid)
    borrower_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    lender_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    borrower = relationship("User", foreign_keys=[borrower_id])
    lender = relationship("User", foreign_keys=[lender_id])
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at", cascade="all, delete-orphan")
    offers = relationship("NegotiationOffer", back_populates="conversation", order_by="NegotiationOffer.created_at", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")

class NegotiationOffer(Base):
    __tablename__ = "negotiation_offers"
    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=True, index=True)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    daily_price = Column(Float, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    total_cost = Column(Float, nullable=False)
    borrower_id_snapshot = Column(String, nullable=True)
    lender_id_snapshot = Column(String, nullable=True)
    daily_rate_paise = Column(BigInteger, nullable=True)
    rental_fee_paise = Column(BigInteger, nullable=True)
    security_deposit_paise = Column(BigInteger, nullable=True)
    total_amount_paise = Column(BigInteger, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(Enum(OfferStatus), default=OfferStatus.pending, index=True)
    parent_offer_id = Column(String, ForeignKey("negotiation_offers.id"), nullable=True)
    borrow_request_id = Column(String, ForeignKey("borrow_requests.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="offers")
    sender = relationship("User")
    borrow_request = relationship("BorrowRequest", back_populates="negotiation_offers")
    listing = relationship("Listing")

# Additive financial entities share the existing metadata/migration lifecycle.
from app.payment_models import (  # noqa: E402,F401
    EscrowLedgerEntry, FinancialAudit, JournalTransaction, PaymentTransaction,
    ProcessedWebhook, RefundAttempt, RefundIntent, RentalBooking, RentalDispute,
)
