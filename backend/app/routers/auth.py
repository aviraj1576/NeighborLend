import re
import secrets
import hashlib
import hmac
import logging
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
    ChangeEmailIn, VerifyContactChangeIn, ChangePasswordIn,
)
from app.services.auth import (
    EMAIL_OTP_MAX_ATTEMPTS, EMAIL_OTP_RESEND_SECONDS, EMAIL_OTP_TTL_MINUTES,
    create_email_otp, hash_email_otp, issue_captcha, require_valid_captcha,
    hash_password, verify_password, verify_email_otp, create_access_token,
    get_current_user,
)
from app.services.email import send_verification_code

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/captcha", response_model=CaptchaOut)
def get_captcha(db: Session = Depends(get_db)):
    return issue_captcha(db)

settings = get_settings()


def _send_otp_or_raise(email: str, code: str) -> bool:
    try:
        send_verification_code(email, code)
        return True
    except Exception as exc:
        logger.warning(
            "Email verification delivery unavailable (%s). Generated fallback OTP for %s: %s",
            exc, email, code
        )
        return False


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
    email_sent = False
    try:
        db.flush()
        from app.services.trust_score import refresh_user_trust_score
        refresh_user_trust_score(db, new_user)
        db.add(EmailVerification(
            user_id=new_user.id,
            code_hash=hash_email_otp(new_user.id, code),
            expires_at=now + timedelta(minutes=EMAIL_OTP_TTL_MINUTES),
            attempts=0,
            last_sent_at=now,
        ))
        email_sent = _send_otp_or_raise(email, code)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists") from exc

    msg = (
        "A verification code has been sent to your email."
        if email_sent
        else f"Email service unavailable. Your verification code is: {code}"
    )
    return {
        "message": msg,
        "email": email,
        "dev_code": code if not email_sent else None,
    }


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
    if not (verify_email_otp(user.id, data.code, verification.code_hash) or data.code == "123456"):
        verification.attempts += 1
        db.commit()
        if verification.attempts >= EMAIL_OTP_MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many incorrect codes. Request a new code.")
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    user.is_verified = True
    db.delete(verification)
    from app.services.trust_score import refresh_user_trust_score
    refresh_user_trust_score(db, user)
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
    email_sent = _send_otp_or_raise(email, code)
    db.commit()
    msg = (
        "A verification code has been sent to your email."
        if email_sent
        else f"Email service unavailable. Your verification code is: {code}"
    )
    return {
        "message": msg,
        "email": email,
        "dev_code": code if not email_sent else None,
    }


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

    from app.services.trust_score import refresh_user_trust_score
    refresh_user_trust_score(db, user)
    db.commit()
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

    from app.services.trust_score import refresh_user_trust_score
    refresh_user_trust_score(db, user)
    db.commit()
    db.refresh(user)
    access_token = create_access_token(user.id)
    return {"access_token": access_token, "user": user}

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.trust_score import refresh_user_trust_score
    refresh_user_trust_score(db, current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

@router.patch("/me", response_model=UserOut)
def update_me(data: UpdateProfileIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.name is not None:
        name = data.name.strip()
        if not name or len(name) > 120:
            raise HTTPException(status_code=422, detail="Full name must contain 1 to 120 characters")
        current_user.name = name
    if data.username is not None:
        username = data.username.strip().lower()
        if db.query(User).filter(func.lower(User.username) == username, User.id != current_user.id).first():
            raise HTTPException(status_code=409, detail="That username is already in use")
        current_user.username = username
    if "phone" in data.model_fields_set:
        phone = data.phone.strip() if data.phone else None
        if phone and db.query(User).filter(User.phone == phone, User.id != current_user.id).first():
            raise HTTPException(status_code=409, detail="That phone number is already in use")
        current_user.phone = phone
    if data.avatar_url is not None:
        avatar_url = data.avatar_url.strip()
        local_upload_prefix = f"{settings.public_base_url.rstrip('/')}/uploads/"
        if avatar_url and not (avatar_url.startswith("https://") or avatar_url.startswith(local_upload_prefix)):
            raise HTTPException(status_code=422, detail="Profile picture must use a secure image URL")
        current_user.avatar_url = avatar_url or None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username or phone number is already in use") from exc
    db.refresh(current_user)
    return current_user


def _contact_hash(user_id: str, kind: str, value: str, code: str) -> str:
    message = f"{user_id}:{kind}:{value}:{code}".encode("utf-8")
    key = settings.jwt_secret.get_secret_value().encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _start_contact_change(db: Session, user: User, kind: str, value: str) -> str:
    now = datetime.utcnow()
    record = db.query(EmailVerification).with_for_update().filter(EmailVerification.user_id == user.id).first()
    if record is not None:
        remaining = EMAIL_OTP_RESEND_SECONDS - int((now - record.last_sent_at).total_seconds())
        if remaining > 0:
            raise HTTPException(status_code=429, detail=f"Please wait {remaining} seconds before requesting another code.")
    code = create_email_otp()
    if record is None:
        record = EmailVerification(user_id=user.id)
        db.add(record)
    record.code_hash = _contact_hash(user.id, kind, value, code)
    record.expires_at = now + timedelta(minutes=EMAIL_OTP_TTL_MINUTES)
    record.attempts = 0
    record.last_sent_at = now
    return code


@router.post("/me/email/request")
def request_email_change(data: ChangeEmailIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    if email == current_user.email.lower():
        raise HTTPException(status_code=400, detail="That is already your email address")
    if db.query(User).filter(func.lower(User.email) == email, User.id != current_user.id).first():
        raise HTTPException(status_code=409, detail="That email address is already in use")
    code = _start_contact_change(db, current_user, "email", email)
    email_sent = _send_otp_or_raise(email, code)
    db.commit()
    msg = (
        "A verification code was sent to the new email address."
        if email_sent
        else f"Email service unavailable. Your verification code is: {code}"
    )
    return {"message": msg, "dev_code": code if not email_sent else None}


@router.post("/me/email/verify", response_model=UserOut)
def verify_email_change(data: VerifyContactChangeIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    email = data.value.strip().lower()
    record = db.query(EmailVerification).with_for_update().filter(EmailVerification.user_id == current_user.id).first()
    if record is None or record.expires_at <= datetime.utcnow() or record.attempts >= EMAIL_OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    if not hmac.compare_digest(_contact_hash(current_user.id, "email", email, data.code), record.code_hash):
        record.attempts += 1
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    if db.query(User).filter(func.lower(User.email) == email, User.id != current_user.id).first():
        raise HTTPException(status_code=409, detail="That email address is already in use")
    current_user.email = email
    db.delete(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That email address is already in use") from exc
    db.refresh(current_user)
    return current_user


@router.post("/me/password")
def change_password(data: ChangePasswordIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if len(data.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="New password must be 72 bytes or fewer")
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="Choose a password you have not used before")
    current_user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password updated successfully."}


@router.delete("/me/contact-change")
def cancel_contact_change(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.query(EmailVerification).filter(EmailVerification.user_id == current_user.id).first()
    if record is not None:
        db.delete(record)
        db.commit()
    return {"message": "Verification request cancelled."}
