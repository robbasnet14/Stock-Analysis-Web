from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.db.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.state import state


router = APIRouter(prefix="/broker", tags=["broker"])
settings = get_settings()


@router.get("/account")
async def account_summary(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if settings.analytics_only_mode:
        raise HTTPException(status_code=410, detail="Broker integration is disabled in analytics-only mode.")
    data = await state.broker.account_summary(db, user)
    return data
