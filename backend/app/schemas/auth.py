from datetime import date
from pydantic import BaseModel, EmailStr


class RegisterIn(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    email: EmailStr
    password: str
    password_confirm: str | None = None
    confirm_password: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    telegram_chat_id: str
    first_name: str = ""
    last_name: str = ""
