from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings


settings = get_settings()


async def get_next_earnings(ticker: str, *, redis_client=None) -> dict[str, Any] | None:
    """Fetch the next earnings date from Finnhub. Cache for 24 hours."""
    symbol = ticker.upper()
    cache_key = f"earnings:{symbol}:v1"
    if redis_client is not None:
        cached = await redis_client.get(cache_key)
        if cached:
            if cached == "null":
                return None
            try:
                return json.loads(cached)
            except Exception:
                pass

    if not settings.finnhub_api_key:
        if redis_client is not None:
            await redis_client.setex(cache_key, 86400, "null")
        return None

    start = date.today()
    end = start + timedelta(days=60)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://finnhub.io/api/v1/calendar/earnings",
                params={"from": start.isoformat(), "to": end.isoformat(), "symbol": symbol, "token": settings.finnhub_api_key},
            )
            resp.raise_for_status()
            rows = resp.json().get("earningsCalendar") or []
    except Exception:
        rows = []

    next_row = None
    for row in rows:
        raw_date = row.get("date")
        if not raw_date:
            continue
        try:
            parsed = date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        if parsed >= start and (next_row is None or parsed < date.fromisoformat(str(next_row["date"]))):
            next_row = {
                "date": parsed.isoformat(),
                "hour": row.get("hour"),
                "epsEstimate": row.get("epsEstimate"),
                "revenueEstimate": row.get("revenueEstimate"),
            }

    if redis_client is not None:
        await redis_client.setex(cache_key, 86400, json.dumps(next_row) if next_row else "null")
    return next_row


def earnings_modifier(next_earnings: dict[str, Any] | None) -> dict[str, Any]:
    if not next_earnings:
        return {"modifier": 1.0, "warning": None}

    try:
        days_until = (date.fromisoformat(str(next_earnings["date"])) - date.today()).days
    except Exception:
        return {"modifier": 1.0, "warning": None}

    if 0 <= days_until <= 5:
        return {
            "modifier": 0.5,
            "warning": f"Earnings in {days_until} days - historical signals less reliable.",
        }
    if -2 <= days_until < 0:
        return {
            "modifier": 0.3,
            "warning": "Just reported earnings - wait 2-3 days for technicals to reset.",
        }
    return {"modifier": 1.0, "warning": None}
