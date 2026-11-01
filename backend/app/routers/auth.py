import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import get_settings
from app.database import get_db
from app.models import EmailVerification, User
from app.schemas.auth import (
    CaptchaOut, RegisterIn, LoginIn, UserOut, TokenOut, UpdateProfileIn,
    RegistrationOut, VerifyEmailIn, ResendVerificationIn, GoogleLoginIn,
)
from app.services.auth import (
    EMAIL_OTP_MAX_ATTEMPTS, EMAIL_OTP_RESEND_SECONDS, EMAIL_OTP_TTL_MINUTES,
    create_email_otp, hash_email_otp, issue_captcha, require_valid_captcha,
    hash_password, verify_password, verify_email_otp, create_access_token,
    get_current_user,
)
from app.services.email import send_verification_code

router = APIRouter()

@router.get("/captcha", response_model=CaptchaOut)
def get_captcha(db: Session = Depends(get_db)):
    return issue_captcha(db)

settings = get_settings()


def _send_otp_or_raise(email: str, code: str) -> None:
    try:
        send_verification_code(email, code)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification is unavailable. Please try again later.",
        ) from exc


def _create_otp_record(db: Session, user: User, now: datetime) -> str:
    code = create_email_otp()
    verification = db.query(EmailVerification).with_for_update().filter(
        EmailVerification.user_id == user.id
    ).first()
    if verification is None:
        verification = EmailVerification(user_id=user.id)
        db.add(verification)
    verification.code_hash = hash_email_otp(user.id, code)
    verification.expires_at = now + timedelta(minutes=EMAIL_OTP_TTL_MINUTES)
    verification.attempts = 0
    verification.last_sent_at = now
    return code


@router.post("/register", response_model=RegistrationOut, status_code=status.HTTP_202_ACCEPTED)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    require_valid_captcha(data.captcha_id, data.captcha_answer, db)

    username = data.username.strip().lower()
    email = str(data.email).strip().lower()
    if db.query(User).filter(
        (func.lower(User.username) == username) | (func.lower(User.email) == email)
    ).first():
        raise HTTPException(status_code=409, detail="Username or email already exists")

    new_user = User(
        name=data.name,
        username=username,
        email=email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        is_verified=False,
    )
    now = datetime.utcnow()
    code = create_email_otp()
    db.add(new_user)
    try:
        db.flush()
        db.add(EmailVerification(
            user_id=new_user.id,
            code_hash=hash_email_otp(new_user.id, code),
            expires_at=now + timedelta(minutes=EMAIL_OTP_TTL_MINUTES),
            attempts=0,
            last_sent_at=now,
        ))
        _send_otp_or_raise(email, code)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists") from exc

    return {"message": "A verification code has been sent to your email.", "email": email}


@router.post("/verify-email", response_model=TokenOut)
def verify_email(data: VerifyEmailIn, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email address is already verified")

    verification = db.query(EmailVerification).with_for_update().filter(
        EmailVerification.user_id == user.id
    ).first()
    if verification is None or verification.expires_at <= datetime.utcnow():
        if verification is not None:
            db.delete(verification)
            db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    if verification.attempts >= EMAIL_OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many incorrect codes. Request a new code.")
    if not verify_email_otp(user.id, data.code, verification.code_hash):
        verification.attempts += 1
        db.commit()
        if verification.attempts >= EMAIL_OTP_MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many incorrect codes. Request a new code.")
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    user.is_verified = True
    db.delete(verification)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user.id), "user": user}


@router.post("/resend-verification", response_model=RegistrationOut)
def resend_verification(data: ResendVerificationIn, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is None or user.is_verified:
        return {
            "message": "If the address belongs to an unverified account, a code has been sent.",
            "email": email,
        }

    now = datetime.utcnow()
    verification = db.query(EmailVerification).with_for_update().filter(
        EmailVerification.user_id == user.id
    ).first()
    if verification is not None:
        seconds_since_last_send = (now - verification.last_sent_at).total_seconds()
        remaining = EMAIL_OTP_RESEND_SECONDS - int(seconds_since_last_send)
        if remaining > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining} seconds before requesting another code.",
                headers={"Retry-After": str(remaining)},
            )

    code = _create_otp_record(db, user, now)
    try:
        _send_otp_or_raise(email, code)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return {"message": "A verification code has been sent to your email.", "email": email}


@router.post("/google", response_model=TokenOut)
def google_login(data: GoogleLoginIn, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is not configured",
        )
    try:
        payload = id_token.verify_oauth2_token(
            data.credential,
            Request(),
            settings.google_client_id,
        )
    except TransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google token verification is temporarily unavailable",
        ) from exc
    except (ValueError, GoogleAuthError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Google credential") from exc

    google_sub = payload.get("sub")
    email = str(payload.get("email", "")).strip().lower()
    if not google_sub or not email or payload.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google account email is not verified")

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user is not None and user.google_sub not in (None, google_sub):
            raise HTTPException(status_code=409, detail="This account is linked to another Google identity")
        if user is None:
            base_username = re.sub(r"[^a-z0-9_.-]", "", email.split("@", 1)[0]) or "neighbor"
            username = base_username[:40]
            while db.query(User).filter(func.lower(User.username) == username).first():
                username = f"{base_username[:39]}-{secrets.token_hex(3)}"
            user = User(
                name=(payload.get("name") or username)[:120],
                username=username,
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                is_verified=True,
                google_sub=google_sub,
            )
            db.add(user)
        else:
            user.google_sub = google_sub
            user.is_verified = True
            verification = db.query(EmailVerification).filter(
                EmailVerification.user_id == user.id
            ).first()
            if verification is not None:
                db.delete(verification)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="This account could not be linked") from exc
        db.refresh(user)

    return {"access_token": create_access_token(user.id), "user": user}

@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == data.username_or_email) | (User.email == data.username_or_email)
    ).first()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")

    access_token = create_access_token(user.id)
    return {"access_token": access_token, "user": user}

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.patch("/me", response_model=UserOut)
def update_me(data: UpdateProfileIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.name is not None:
        current_user.name = data.name
    if data.phone is not None:
        current_user.phone = data.phone
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url
        
    db.commit()
    db.refresh(current_user)
    return current_user
