from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies import get_current_user
from app.models.alert import AlertFire, AlertSubscription
from app.models.user import User


router = APIRouter(prefix="/alerts", tags=["alerts"])

ConditionType = Literal["price_above", "price_below", "ema_cross", "signal_flip", "news_impact", "earnings_upcoming"]
Channel = Literal["email", "telegram", "web"]


class AlertCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    condition_type: ConditionType
    condition_params: dict[str, Any] = Field(default_factory=dict)
    channel: Channel = "web"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_params(self) -> "AlertCreate":
        params = self.condition_params or {}
        if self.condition_type in {"price_above", "price_below"} and float(params.get("target") or 0) <= 0:
            raise ValueError("target must be greater than 0")
        if self.condition_type == "ema_cross":
            if int(params.get("ema") or 0) not in {20, 50, 100, 200}:
                raise ValueError("ema must be one of 20, 50, 100, 200")
            if str(params.get("direction") or "") not in {"above", "below"}:
                raise ValueError("direction must be above or below")
        if self.condition_type == "signal_flip":
            if str(params.get("horizon") or "") not in {"short", "mid", "long"}:
                raise ValueError("horizon must be short, mid, or long")
            if str(params.get("to") or "") not in {"bullish", "bearish"}:
                raise ValueError("to must be bullish or bearish")
        if self.condition_type == "news_impact":
            if float(params.get("min_impact") or 0) <= 0:
                raise ValueError("min_impact must be greater than 0")
            if str(params.get("sentiment") or "any") not in {"any", "bullish", "bearish"}:
                raise ValueError("sentiment must be any, bullish, or bearish")
        if self.condition_type == "earnings_upcoming" and int(params.get("days_before") or 0) <= 0:
            raise ValueError("days_before must be greater than 0")
        return self


class AlertPatch(BaseModel):
    condition_params: dict[str, Any] | None = None
    channel: Channel | None = None
    enabled: bool | None = None


def _alert_out(row: AlertSubscription) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "user_id": int(row.user_id),
        "ticker": row.ticker,
        "condition_type": row.condition_type,
        "condition_params": row.condition_params or {},
        "channel": row.channel,
        "enabled": bool(row.enabled),
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else row.created_at,
        "last_fired_at": row.last_fired_at.isoformat() if isinstance(row.last_fired_at, datetime) else row.last_fired_at,
    }


def _fire_out(row: AlertFire) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "alert_id": int(row.alert_id) if row.alert_id is not None else None,
        "ticker": row.ticker,
        "condition_type": row.condition_type,
        "condition_summary": row.condition_summary,
        "message": row.message,
        "payload": row.payload or {},
        "channel": row.channel,
        "fired_at": row.fired_at.isoformat() if isinstance(row.fired_at, datetime) else row.fired_at,
        "read_at": row.read_at.isoformat() if isinstance(row.read_at, datetime) else row.read_at,
    }


@router.get("")
async def list_alerts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    stmt = select(AlertSubscription).where(AlertSubscription.user_id == user.id).order_by(AlertSubscription.created_at.desc(), AlertSubscription.id.desc())
    rows = list((await db.execute(stmt)).scalars().all())
    return {"alerts": [_alert_out(row) for row in rows]}


@router.post("")
async def create_alert(payload: AlertCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    row = AlertSubscription(
        user_id=user.id,
        ticker=payload.ticker.upper().strip(),
        condition_type=payload.condition_type,
        condition_params=payload.condition_params,
        channel=payload.channel,
        enabled=payload.enabled,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _alert_out(row)


@router.patch("/{alert_id}")
async def update_alert(alert_id: int, payload: AlertPatch, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    row = await db.get(AlertSubscription, alert_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    if payload.condition_params is not None:
        row.condition_params = payload.condition_params
    if payload.channel is not None:
        row.channel = payload.channel
    if payload.enabled is not None:
        row.enabled = payload.enabled
    await db.commit()
    await db.refresh(row)
    return _alert_out(row)


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    row = await db.get(AlertSubscription, alert_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/history")
async def alert_history(limit: int = 50, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    capped = max(1, min(100, int(limit)))
    stmt = select(AlertFire).where(AlertFire.user_id == user.id).order_by(AlertFire.fired_at.desc(), AlertFire.id.desc()).limit(capped)
    rows = list((await db.execute(stmt)).scalars().all())
    return {"items": [_fire_out(row) for row in rows]}
