from datetime import date, datetime, timedelta
import uuid
import re
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.auth_token import RefreshToken
from app.models.user import User
from app.models.user_profile import UserProfile


settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def _encode_token(payload: dict, expires_minutes: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    body = {**payload, "exp": expire}
    return jwt.encode(body, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(sub: str, role: str) -> str:
    return _encode_token({"sub": sub, "role": role, "type": "access"}, settings.jwt_expire_minutes)


async def create_refresh_token(db: AsyncSession, user_id: int) -> str:
    jti = uuid.uuid4().hex
    token = _encode_token({"sub": str(user_id), "jti": jti, "type": "refresh"}, settings.jwt_expire_minutes * 10)
    record = RefreshToken(
        user_id=user_id,
        token_jti=jti,
        revoked=False,
        expires_at=datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes * 10),
    )
    db.add(record)
    await db.commit()
    return token


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def validate_refresh_token(db: AsyncSession, refresh_token: str) -> User | None:
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            return None
        user_id = int(payload.get("sub"))
        jti = str(payload.get("jti"))
    except (JWTError, ValueError, TypeError):
        return None

    stmt = select(RefreshToken).where(RefreshToken.token_jti == jti, RefreshToken.revoked == False)  # noqa: E712
    token_row = (await db.execute(stmt)).scalar_one_or_none()
    if token_row is None or token_row.expires_at < datetime.utcnow():
        return None

    return await db.get(User, user_id)


async def revoke_refresh_token(db: AsyncSession, refresh_token: str) -> bool:
    try:
        payload = decode_token(refresh_token)
        jti = str(payload.get("jti"))
    except Exception:
        return False

    stmt = select(RefreshToken).where(RefreshToken.token_jti == jti)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False

    row.revoked = True
    await db.commit()
    return True


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email.lower())
    return (await db.execute(stmt)).scalar_one_or_none()


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or fewer.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must include at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must include at least one lowercase letter.")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must include at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must include at least one special character.")


def validate_age_18_plus(dob: date) -> None:
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 18:
        raise ValueError("You must be at least 18 years old to register.")


async def get_profile_by_user_id(db: AsyncSession, user_id: int) -> UserProfile | None:
    stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def ensure_profile(db: AsyncSession, user: User) -> UserProfile:
    profile = await get_profile_by_user_id(db, user.id)
    if profile:
        return profile
    profile = UserProfile(user_id=user.id, first_name="", last_name="", date_of_birth=None, watchlist_csv="")
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def create_user(db: AsyncSession, email: str, password: str, first_name: str, last_name: str, date_of_birth: date) -> User:
    existing_count = await db.scalar(select(func.count(User.id)))
    role = "admin" if (existing_count or 0) == 0 else "trader"
    user = User(email=email.lower(), hashed_password=hash_password(password), role=role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    profile = UserProfile(
        user_id=user.id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        date_of_birth=date_of_birth,
        watchlist_csv="",
    )
    db.add(profile)
    await db.commit()
    return user


async def issue_token_pair(db: AsyncSession, user: User) -> dict:
    access = create_access_token(str(user.id), user.role)
    refresh = await create_refresh_token(db, user.id)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}
