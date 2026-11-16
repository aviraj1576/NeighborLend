from datetime import datetime
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class CaptchaOut(BaseModel):
    captcha_id: str
    question: str

class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(..., min_length=6)
    captcha_id: str
    captcha_answer: Union[int, str]


class RegistrationOut(BaseModel):
    message: str
    email: EmailStr


class VerifyEmailIn(BaseModel):
    email: EmailStr
    code: str = Field(..., pattern=r"^[0-9]{6}$")


class ResendVerificationIn(BaseModel):
    email: EmailStr


class GoogleLoginIn(BaseModel):
    credential: str = Field(..., min_length=1)

class LoginIn(BaseModel):
    username_or_email: str
    password: str

class UserOut(BaseModel):
    id: str
    name: str
    username: str
    email: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    trust_score: float
    avg_rating: float
    rating_count: int
    completed_rentals_count: int
    is_admin: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class UpdateProfileIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    username: Optional[str] = Field(default=None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    avatar_url: Optional[str] = Field(default=None, max_length=2048)

class ChangeEmailIn(BaseModel):
    email: EmailStr

class VerifyContactChangeIn(BaseModel):
    value: str = Field(..., min_length=3, max_length=254)
    code: str = Field(..., pattern=r"^[0-9]{6}$")

class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=72)

class ChangePhoneIn(BaseModel):
    phone: str = Field(..., min_length=8, max_length=20, pattern=r"^\+[1-9][0-9]{7,14}$")
