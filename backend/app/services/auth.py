import hashlib
import hmac
import secrets
import uuid
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Union
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.models import CaptchaChallenge, User

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
CAPTCHA_TTL_MINUTES = 5
EMAIL_OTP_TTL_MINUTES = 10
EMAIL_OTP_RESEND_SECONDS = 60
EMAIL_OTP_MAX_ATTEMPTS = 5

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    hash_bytes = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_email_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_email_otp(user_id: str, code: str) -> str:
    message = f"{user_id}:{code}".encode("utf-8")
    return hmac.new(settings.jwt_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_email_otp(user_id: str, code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_email_otp(user_id, code), expected_hash)

def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_verified:
        raise credentials_exception
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

def issue_captcha(db: Session) -> dict:
    import random
    now = datetime.utcnow()
    db.query(CaptchaChallenge).filter(CaptchaChallenge.expires_at <= now).delete(
        synchronize_session=False
    )
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    captcha_id = str(uuid.uuid4())
    question = f"{num1} + {num2} = ?"
    db.add(CaptchaChallenge(
        id=captcha_id,
        answer=num1 + num2,
        expires_at=now + timedelta(minutes=CAPTCHA_TTL_MINUTES),
    ))
    db.commit()
    return {"captcha_id": captcha_id, "question": question}

def verify_captcha(
    captcha_id: str,
    answer: Optional[Union[int, str]],
    db: Session,
) -> bool:
    challenge = (
        db.query(CaptchaChallenge)
        .filter(CaptchaChallenge.id == captcha_id)
        .with_for_update()
        .first()
    )
    if challenge is None:
        return False

    is_valid = False
    try:
        is_valid = (
            challenge.expires_at > datetime.utcnow()
            and int(answer) == challenge.answer
        )
    except (ValueError, TypeError):
        pass

    db.delete(challenge)
    db.commit()
    return is_valid

def require_valid_captcha(
    captcha_id: str,
    answer: Optional[Union[int, str]],
    db: Session,
):
    if not verify_captcha(captcha_id, answer, db):
        raise HTTPException(status_code=400, detail="Invalid captcha")
