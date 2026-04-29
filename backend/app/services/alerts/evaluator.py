from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertFire, AlertSubscription
from app.models.news import NewsArticle
from app.models.signal_snapshot import SignalSnapshot
from app.models.user import User
from app.services.signals.earnings import get_next_earnings
from app.state import state


logger = logging.getLogger(__name__)
RATE_LIMIT = timedelta(minutes=60)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _condition_summary(alert: AlertSubscription) -> str:
    params = alert.condition_params or {}
    if alert.condition_type == "price_above":
        return f"price above ${float(params.get('target', 0)):.2f}"
    if alert.condition_type == "price_below":
        return f"price below ${float(params.get('target', 0)):.2f}"
    if alert.condition_type == "ema_cross":
        return f"{params.get('ema', 200)}-EMA cross {params.get('direction', 'above')}"
    if alert.condition_type == "signal_flip":
        return f"{params.get('horizon', 'mid')} signal flips to {params.get('to', 'bullish')}"
    if alert.condition_type == "news_impact":
        return f"news impact >= {params.get('min_impact', 8)}"
    if alert.condition_type == "earnings_upcoming":
        return f"earnings within {params.get('days_before', 5)} days"
    return alert.condition_type


async def _latest_price(ticker: str, fallback: float | None = None) -> float | None:
    symbol = ticker.upper()
    if state.redis is not None:
        raw = await state.redis.hget("price:latest", symbol)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
        raw = await state.redis.get(f"price:{symbol}")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
        cached = await state.redis.get(f"latest:{symbol}")
        if cached:
            try:
                return float(json.loads(cached).get("price"))
            except Exception:
                pass
    return fallback


def _rate_limited(alert: AlertSubscription, now: datetime) -> bool:
    return bool(alert.last_fired_at and now - alert.last_fired_at.replace(tzinfo=None) < RATE_LIMIT)


async def _fire_alert(db: AsyncSession, alert: AlertSubscription, user: User, price: float | None, extra: dict[str, Any]) -> None:
    now = _utcnow()
    if _rate_limited(alert, now):
        return

    summary = _condition_summary(alert)
    message = f"{alert.ticker}: {summary}"
    payload = {
        "type": "alert_fired",
        "alert_id": int(alert.id),
        "ticker": alert.ticker,
        "condition_type": alert.condition_type,
        "condition_summary": summary,
        "price": price,
        "channel": alert.channel,
        "fired_at": now.isoformat(),
        **extra,
    }
    row = AlertFire(
        alert_id=alert.id,
        user_id=alert.user_id,
        ticker=alert.ticker,
        condition_type=alert.condition_type,
        condition_summary=summary,
        message=message,
        payload=payload,
        channel=alert.channel,
        fired_at=now,
    )
    alert.last_fired_at = now
    db.add(row)
    await db.flush()
    payload["fire_id"] = int(row.id)

    if state.redis is not None:
        await state.redis.publish(f"alerts:{alert.user_id}", json.dumps(payload, default=str))

    if alert.channel == "email":
        subject = f"🔔 [Stock Web] {alert.ticker}: {summary}"
        lines = [
            f"Your alert fired:\n\n"
            f"Ticker: {alert.ticker}\n"
            f"Condition: {summary}\n"
        ]
        if price is not None:
            lines.append(f"Current price: ${price:.2f}\n")
        lines.append(f"Triggered at: {now.isoformat()}\n\nView on Stock Web: /signals/{alert.ticker}")
        await state.notifications.enqueue("email", user.email, "".join(lines), subject=subject)
    elif alert.channel == "telegram":
        await state.notifications.enqueue("telegram", user.telegram_chat_id or "", f"{message}\nPrice: ${price:.2f}" if price is not None else message)


async def _evaluate_price(alerts: list[AlertSubscription], users: dict[int, User], db: AsyncSession) -> None:
    for alert in alerts:
        price = await _latest_price(alert.ticker)
        if price is None:
            continue
        target = float((alert.condition_params or {}).get("target") or 0)
        fired = (alert.condition_type == "price_above" and price >= target) or (alert.condition_type == "price_below" and price <= target)
        if fired and alert.user_id in users:
            await _fire_alert(db, alert, users[alert.user_id], price, {"target": target})


async def _evaluate_ema_cross(alerts: list[AlertSubscription], users: dict[int, User], db: AsyncSession) -> None:
    by_ticker: dict[str, list[AlertSubscription]] = defaultdict(list)
    for alert in alerts:
        by_ticker[alert.ticker.upper()].append(alert)

    for ticker, rows in by_ticker.items():
        try:
            payload = await state.market_data.get_bars(ticker, "1Y", tf="1Day", max_points=260)
            bars = payload.get("bars") or []
            close = pd.Series([float(b.get("close") or b.get("price") or 0.0) for b in bars])
        except Exception:
            continue
        if len(close) < 3:
            continue

        price = float(close.iloc[-1])
        for alert in rows:
            params = alert.condition_params or {}
            span = int(params.get("ema") or 200)
            if len(close) < span:
                continue
            ema = close.ewm(span=span, adjust=False, min_periods=span).mean()
            prev_above = close.iloc[-2] > ema.iloc[-2]
            now_above = close.iloc[-1] > ema.iloc[-1]
            direction = str(params.get("direction") or "above")
            fired = direction == "above" and (not prev_above) and now_above
            fired = fired or (direction == "below" and prev_above and not now_above)
            if fired and alert.user_id in users:
                await _fire_alert(db, alert, users[alert.user_id], price, {"ema": span, "direction": direction})


async def _evaluate_signal_flip(alerts: list[AlertSubscription], users: dict[int, User], db: AsyncSession) -> None:
    for alert in alerts:
        params = alert.condition_params or {}
        horizon = str(params.get("horizon") or "mid")
        target = str(params.get("to") or "bullish").lower()
        since = alert.last_fired_at or (datetime.utcnow() - timedelta(hours=2))
        stmt = (
            select(SignalSnapshot)
            .where(
                SignalSnapshot.ticker == alert.ticker.upper(),
                SignalSnapshot.horizon == horizon,
                SignalSnapshot.track == "ensemble",
                SignalSnapshot.computed_at >= since,
            )
            .order_by(SignalSnapshot.computed_at.desc())
            .limit(2)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        if not rows:
            continue
        latest = str(rows[0].action).lower()
        previous = str(rows[1].action).lower() if len(rows) > 1 else ""
        if latest == target and previous != target and alert.user_id in users:
            await _fire_alert(db, alert, users[alert.user_id], None, {"horizon": horizon, "to": target})


async def _evaluate_news(alerts: list[AlertSubscription], users: dict[int, User], db: AsyncSession) -> None:
    for alert in alerts:
        params = alert.condition_params or {}
        since = alert.last_fired_at or (datetime.utcnow() - timedelta(hours=24))
        sentiment = str(params.get("sentiment") or "any").lower()
        min_impact = float(params.get("min_impact") or 8)
        stmt = (
            select(NewsArticle)
            .where(NewsArticle.ticker == alert.ticker.upper(), NewsArticle.published_at >= since)
            .order_by(NewsArticle.published_at.desc())
            .limit(20)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        for article in rows:
            score = float(article.sentiment_score or 0.0)
            impact = abs(score) * 10.0
            label_ok = sentiment == "any" or (sentiment == "bullish" and score > 0) or (sentiment == "bearish" and score < 0)
            if impact >= min_impact and label_ok and alert.user_id in users:
                await _fire_alert(db, alert, users[alert.user_id], await _latest_price(alert.ticker), {"headline": article.headline, "impact": impact})
                break


async def _evaluate_earnings(alerts: list[AlertSubscription], users: dict[int, User], db: AsyncSession) -> None:
    today = datetime.utcnow().date()
    for alert in alerts:
        params = alert.condition_params or {}
        days_before = int(params.get("days_before") or 5)
        earnings = await get_next_earnings(alert.ticker, redis_client=state.redis)
        if not earnings or not earnings.get("date"):
            continue
        try:
            days_until = (datetime.fromisoformat(str(earnings["date"])).date() - today).days
        except ValueError:
            continue
        if 0 <= days_until <= days_before and alert.user_id in users:
            await _fire_alert(db, alert, users[alert.user_id], await _latest_price(alert.ticker), {"next_earnings": earnings, "days_until": days_until})


async def evaluate_alerts_once(db: AsyncSession) -> int:
    stmt = select(AlertSubscription).where(AlertSubscription.enabled.is_(True)).order_by(AlertSubscription.condition_type, AlertSubscription.id)
    alerts = list((await db.execute(stmt)).scalars().all())
    if not alerts:
        return 0

    user_ids = sorted({int(a.user_id) for a in alerts})
    user_rows = list((await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all())
    users = {int(u.id): u for u in user_rows}
    grouped: dict[str, list[AlertSubscription]] = defaultdict(list)
    for alert in alerts:
        grouped[alert.condition_type].append(alert)

    await _evaluate_price(grouped.get("price_above", []) + grouped.get("price_below", []), users, db)
    await _evaluate_ema_cross(grouped.get("ema_cross", []), users, db)
    await _evaluate_signal_flip(grouped.get("signal_flip", []), users, db)
    await _evaluate_news(grouped.get("news_impact", []), users, db)
    await _evaluate_earnings(grouped.get("earnings_upcoming", []), users, db)
    await db.commit()
    return len(alerts)
