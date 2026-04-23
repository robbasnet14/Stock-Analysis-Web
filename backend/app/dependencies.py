from collections.abc import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.user import User
from app.services.auth_service import decode_token


security = HTTPBearer(auto_error=False)
GUEST_ROLE = "guest"


def _guest_user() -> User:
    return User(id=0, email="guest@local", hashed_password="", role=GUEST_ROLE, telegram_chat_id=None)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required. Please sign in to access this resource.")

    token = creds.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found")
    return user


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if creds is None:
        return None
    token = creds.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None
    return await db.get(User, user_id)


async def get_user_or_guest(
    user: User | None = Depends(get_optional_user),
) -> User:
    return user if user is not None else _guest_user()


def require_roles(*roles: str) -> Callable:
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker
