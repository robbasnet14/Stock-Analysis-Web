import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.services.auth_service import (
    ensure_profile,
    get_user_by_email,
    create_user,
    validate_age_18_plus,
    validate_password_strength,
    verify_password,
    issue_token_pair,
    revoke_refresh_token,
    validate_refresh_token,
)


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _field_error(field: str, msg: str) -> dict:
    return {"loc": ["body", field], "msg": msg, "type": "value_error"}


@router.post("/register", response_model=TokenOut)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    existing = await get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail=[_field_error("email", "Email already exists")])

    password_confirm = payload.password_confirm or payload.confirm_password
    if not password_confirm:
        raise HTTPException(status_code=400, detail=[_field_error("password_confirm", "Please confirm your password.")])

    if payload.password != password_confirm:
        raise HTTPException(status_code=400, detail=[_field_error("password_confirm", "Passwords do not match")])
    try:
        validate_password_strength(payload.password)
        validate_age_18_plus(payload.date_of_birth)
    except ValueError as exc:
        msg = str(exc)
        if "Password" in msg:
            field = "password"
        elif "18" in msg or "years old" in msg:
            field = "date_of_birth"
        else:
            field = "email"
        raise HTTPException(status_code=400, detail=[_field_error(field, msg)]) from exc

    try:
        user = await create_user(
            db,
            payload.email,
            payload.password,
            payload.first_name,
            payload.last_name,
            payload.date_of_birth,
        )
        token_pair = await issue_token_pair(db, user)
    except Exception:
        await db.rollback()
        logger.exception("auth register failed for email=%s", payload.email)
        raise
    return TokenOut(**token_pair)


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    user = await get_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token_pair = await issue_token_pair(db, user)
    return TokenOut(**token_pair)


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    user = await validate_refresh_token(db, payload.refresh_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    await revoke_refresh_token(db, payload.refresh_token)
    token_pair = await issue_token_pair(db, user)
    return TokenOut(**token_pair)


@router.post("/logout")
async def logout(payload: RefreshIn, db: AsyncSession = Depends(get_db)) -> dict:
    ok = await revoke_refresh_token(db, payload.refresh_token)
    return {"ok": ok}


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserOut:
    profile = await ensure_profile(db, current)
    first_name = profile.first_name
    last_name = profile.last_name
    return UserOut(
        id=current.id,
        email=current.email,
        role=current.role,
        telegram_chat_id=current.telegram_chat_id,
        first_name=first_name,
        last_name=last_name,
    )


@router.post("/telegram")
async def set_telegram_chat_id(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    current.telegram_chat_id = chat_id.strip()
    await db.commit()
    return {"ok": True, "telegram_chat_id": current.telegram_chat_id}
