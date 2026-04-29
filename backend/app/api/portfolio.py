import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.db.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.holdings_lot import HoldingsLot
from app.models.portfolio import PaperOrder, PortfolioPosition
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.corporate_action import DividendEvent, StockSplit, UserDividendCredit
from app.models.user import User
from app.schemas.portfolio import OrderIn, PositionIn, PositionOut
from app.services.portfolio import RANGE_CONFIG, compute_portfolio_timeseries
from app.state import state


router = APIRouter(prefix="/portfolio", tags=["portfolio"])
settings = get_settings()

class HoldingLotIn(BaseModel):
    ticker: str
    shares: float = Field(gt=0)
    buy_price: float = Field(gt=0)
    buy_ts: datetime | None = None
    merge_mode: Literal["ask", "merge", "new_lot"] = "ask"


class HoldingLotPatch(BaseModel):
    shares: float = Field(ge=0)
    buy_price: float = Field(gt=0)
    buy_ts: datetime | None = None


def _to_position_out_from_lot(lot: HoldingsLot) -> PositionOut:
    return PositionOut(
        id=int(lot.id),
        ticker=str(lot.ticker).upper(),
        quantity=float(lot.remaining_shares or lot.shares or 0.0),
        avg_cost=float(lot.buy_price or 0.0),
        updated_at=lot.buy_ts if isinstance(lot.buy_ts, datetime) else datetime.utcnow(),
    )


def _normalize_quote_payload(symbol: str, payload: dict) -> dict:
    px = float(payload.get("price") or 0.0)
    open_px = float(payload.get("open_price") or px)
    high_px = float(payload.get("high_price") or px or open_px)
    low_px = float(payload.get("low_price") or px or open_px)
    ts = payload.get("timestamp")
    if not isinstance(ts, datetime):
        ts = datetime.utcnow()
    return {
        "ticker": symbol.upper(),
        "price": px,
        "change_percent": float(payload.get("change_percent") or 0.0),
        "volume": int(float(payload.get("volume") or 0)),
        "open_price": open_px,
        "high_price": high_px,
        "low_price": low_px,
        "timestamp": ts,
        "source": str(payload.get("source") or "provider_router"),
        "is_live": True,
    }


def _normalize_header(name: str) -> str:
    return " ".join((name or "").strip().lower().replace("_", " ").split())


def _pick_value(row: dict[str, str], aliases: list[str]) -> str:
    normalized = {_normalize_header(k): (v or "").strip() for k, v in row.items()}
    for alias in aliases:
        val = normalized.get(_normalize_header(alias), "")
        if val:
            return val
    return ""


async def _broadcast_order(user_id: int, order: PaperOrder) -> None:
    await state.order_websocket.broadcast(
        user_id,
        {
            "type": "order_update",
            "order": {
                "id": order.id,
                "ticker": order.ticker,
                "side": order.side,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "requested_price": order.requested_price,
                "filled_price": order.filled_price,
                "status": order.status,
                "broker_mode": order.broker_mode,
                "broker_order_id": order.broker_order_id,
                "created_at": order.created_at,
            },
        },
    )


@router.get("/positions", response_model=list[PositionOut])
async def list_positions(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    lot_stmt = (
        select(HoldingsLot)
        .where(HoldingsLot.user_id == user.id, HoldingsLot.status == "open")
        .order_by(HoldingsLot.created_at.desc(), HoldingsLot.id.desc())
    )
    lots = list((await db.execute(lot_stmt)).scalars().all())
    if lots:
        return [_to_position_out_from_lot(lot) for lot in lots]

    stmt = select(PortfolioPosition).where(PortfolioPosition.user_id == user.id).order_by(PortfolioPosition.updated_at.desc())
    rows = list((await db.execute(stmt)).scalars().all())
    return [PositionOut(id=r.id, ticker=r.ticker, quantity=r.quantity, avg_cost=r.avg_cost, updated_at=r.updated_at) for r in rows]


@router.get("/holdings", response_model=list[PositionOut])
async def list_holdings_lots(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(HoldingsLot)
        .where(HoldingsLot.user_id == user.id, HoldingsLot.status == "open")
        .order_by(HoldingsLot.created_at.desc(), HoldingsLot.id.desc())
    )
    lots = list((await db.execute(stmt)).scalars().all())
    return [_to_position_out_from_lot(lot) for lot in lots]


@router.post("/holdings", response_model=PositionOut)
async def add_holding_lot(
    payload: HoldingLotIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    ticker = payload.ticker.upper().strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")

    stmt = (
        select(HoldingsLot)
        .where(HoldingsLot.user_id == user.id, HoldingsLot.ticker == ticker, HoldingsLot.status == "open")
        .order_by(HoldingsLot.created_at.asc(), HoldingsLot.id.asc())
    )
    existing_lots = list((await db.execute(stmt)).scalars().all())
    if existing_lots and payload.merge_mode == "ask":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_ticker",
                "message": f"You already hold {ticker}. Choose merge or add as new lot.",
            },
        )

    buy_ts = payload.buy_ts or datetime.utcnow()
    if existing_lots and payload.merge_mode == "merge":
        target = existing_lots[0]
        prev_qty = float(target.remaining_shares or target.shares or 0.0)
        new_qty = float(payload.shares)
        total_qty = prev_qty + new_qty
        prev_cost = float(target.buy_price or 0.0) * prev_qty
        new_cost = float(payload.buy_price) * new_qty
        target.remaining_shares = total_qty
        target.shares = total_qty
        target.buy_price = (prev_cost + new_cost) / total_qty if total_qty > 0 else float(payload.buy_price)
        target.buy_ts = buy_ts
        await db.commit()
        await db.refresh(target)
        return _to_position_out_from_lot(target)

    lot = HoldingsLot(
        user_id=user.id,
        ticker=ticker,
        asset_class="crypto" if "-USD" in ticker or ticker.endswith("USDT") else "equity",
        shares=float(payload.shares),
        remaining_shares=float(payload.shares),
        buy_price=float(payload.buy_price),
        buy_ts=buy_ts,
        status="open",
    )
    db.add(lot)
    await db.commit()
    await db.refresh(lot)
    return _to_position_out_from_lot(lot)


@router.patch("/holdings/{lot_id}")
async def patch_holding_lot(
    lot_id: int,
    payload: HoldingLotPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    lot = await db.get(HoldingsLot, lot_id)
    if lot is None or lot.user_id != user.id or lot.status != "open":
        raise HTTPException(status_code=404, detail="Holding not found")

    if payload.shares <= 0:
        await db.delete(lot)
        await db.commit()
        return {"removed": True}

    lot.shares = float(payload.shares)
    lot.remaining_shares = float(payload.shares)
    lot.buy_price = float(payload.buy_price)
    lot.buy_ts = payload.buy_ts or lot.buy_ts or datetime.utcnow()
    await db.commit()
    await db.refresh(lot)
    return {"removed": False, "holding": _to_position_out_from_lot(lot).model_dump()}


@router.delete("/holdings/{lot_id}")
async def delete_holding_lot(
    lot_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    lot = await db.get(HoldingsLot, lot_id)
    if lot is None or lot.user_id != user.id:
        raise HTTPException(status_code=404, detail="Holding not found")
    await db.delete(lot)
    await db.commit()
    return {"ok": True}


@router.get("/value-history")
async def portfolio_value_history(
    range: str = "1D",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    range_key = (range or "1D").upper()
    if range_key not in RANGE_CONFIG:
        raise HTTPException(status_code=400, detail="range must be one of 1D, 1W, 1M, 3M, 1Y, ALL")
    points = await compute_portfolio_timeseries(
        db=db,
        market_data=state.market_data,
        redis_client=state.redis,
        user_id=int(user.id),
        range_key=range_key,
    )
    data = [
        {
            "price": round(float(point["value"]), 4),
            "volume": 0.0,
            "change_percent": 0.0,
            "open_price": round(float(point["value"]), 4),
            "high_price": round(float(point["value"]), 4),
            "low_price": round(float(point["value"]), 4),
            "timestamp": datetime.fromtimestamp(int(point["time"]), tz=timezone.utc),
        }
        for point in points
    ]
    return {"range": range_key, "data": data}


@router.get("/timeseries")
async def portfolio_timeseries(
    range: str = "1D",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    range_key = (range or "1D").upper()
    if range_key not in RANGE_CONFIG:
        raise HTTPException(status_code=400, detail="range must be one of 1D,1W,1M,3M,1Y,ALL")
    return await compute_portfolio_timeseries(
        db=db,
        market_data=state.market_data,
        redis_client=state.redis,
        user_id=int(user.id),
        range_key=range_key,
    )


@router.get("/history")
async def portfolio_snapshot_history(
    range: str = "1D",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = range.upper()
    if r == "1D":
        cutoff = datetime.utcnow() - timedelta(days=1)
    elif r == "1W":
        cutoff = datetime.utcnow() - timedelta(days=7)
    elif r == "1M":
        cutoff = datetime.utcnow() - timedelta(days=31)
    elif r == "3M":
        cutoff = datetime.utcnow() - timedelta(days=93)
    elif r == "1Y":
        cutoff = datetime.utcnow() - timedelta(days=366)
    elif r == "ALL":
        cutoff = datetime.utcnow() - timedelta(days=3650)
    else:
        raise HTTPException(status_code=400, detail="range must be one of 1D, 1W, 1M, 3M, 1Y, ALL")

    stmt = (
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.user_id == user.id, PortfolioSnapshot.timestamp >= cutoff)
        .order_by(PortfolioSnapshot.timestamp.asc())
        .limit(10000)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return {
        "range": r,
        "data": [
            {
                "price": float(row.value),
                "volume": 0.0,
                "change_percent": 0.0,
                "open_price": float(row.value),
                "high_price": float(row.value),
                "low_price": float(row.value),
                "timestamp": row.timestamp,
            }
            for row in rows
        ],
    }


@router.get("/corporate-actions/recent")
async def corporate_actions_recent(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    split_stmt = (
        select(StockSplit)
        .order_by(StockSplit.effective_date.desc(), StockSplit.created_at.desc())
        .limit(50)
    )
    dividend_stmt = (
        select(DividendEvent)
        .order_by(DividendEvent.pay_date.desc(), DividendEvent.created_at.desc())
        .limit(50)
    )
    credit_stmt = (
        select(UserDividendCredit)
        .where(UserDividendCredit.user_id == user.id)
        .order_by(UserDividendCredit.pay_date.desc(), UserDividendCredit.created_at.desc())
        .limit(50)
    )
    splits = list((await db.execute(split_stmt)).scalars().all())
    dividends = list((await db.execute(dividend_stmt)).scalars().all())
    credits = list((await db.execute(credit_stmt)).scalars().all())
    return {
        "splits": [
            {
                "ticker": s.ticker,
                "effective_date": s.effective_date,
                "from_factor": s.from_factor,
                "to_factor": s.to_factor,
                "applied": s.applied,
            }
            for s in splits
        ],
        "dividends": [
            {
                "ticker": d.ticker,
                "ex_date": d.ex_date,
                "pay_date": d.pay_date,
                "cash_amount": d.cash_amount,
                "applied": d.applied,
            }
            for d in dividends
        ],
        "user_dividend_credits": [
            {
                "ticker": c.ticker,
                "pay_date": c.pay_date,
                "amount": c.amount,
                "created_at": c.created_at,
            }
            for c in credits
        ],
    }


@router.post("/import-csv")
async def import_positions_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV decode failed: {exc}") from exc

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is missing a header row")

    merged: dict[str, dict[str, float]] = {}
    errors: list[str] = []

    for idx, row in enumerate(reader, start=2):
        ticker = _pick_value(row, ["ticker", "symbol", "stock", "instrument"])
        qty_raw = _pick_value(row, ["quantity", "qty", "shares", "share quantity"])
        avg_raw = _pick_value(
            row,
            ["avg cost", "average cost", "average price", "avg price", "cost basis per share", "price"],
        )
        total_raw = _pick_value(row, ["cost basis", "total cost", "total value", "market value"])

        if not ticker:
            errors.append(f"line {idx}: missing ticker/symbol")
            continue

        try:
            qty = float(qty_raw.replace(",", ""))
        except Exception:
            errors.append(f"line {idx}: invalid quantity '{qty_raw}'")
            continue

        if qty <= 0:
            errors.append(f"line {idx}: quantity must be > 0")
            continue

        if avg_raw:
            try:
                avg_cost = float(avg_raw.replace(",", "").replace("$", ""))
            except Exception:
                errors.append(f"line {idx}: invalid average cost '{avg_raw}'")
                continue
        elif total_raw:
            try:
                total_cost = float(total_raw.replace(",", "").replace("$", ""))
                avg_cost = total_cost / qty if qty else 0.0
            except Exception:
                errors.append(f"line {idx}: invalid total cost '{total_raw}'")
                continue
        else:
            errors.append(f"line {idx}: missing average cost or total cost")
            continue

        symbol = ticker.upper()
        existing = merged.get(symbol)
        if existing is None:
            merged[symbol] = {"qty": qty, "cost_value": avg_cost * qty}
        else:
            existing["qty"] += qty
            existing["cost_value"] += avg_cost * qty

    imported = 0
    for symbol, agg in merged.items():
        qty = agg["qty"]
        avg_cost = agg["cost_value"] / qty if qty else 0.0
        stmt = select(PortfolioPosition).where(PortfolioPosition.user_id == user.id, PortfolioPosition.ticker == symbol)
        pos = (await db.execute(stmt)).scalar_one_or_none()
        if pos is None:
            pos = PortfolioPosition(
                user_id=user.id,
                ticker=symbol,
                quantity=qty,
                avg_cost=avg_cost,
                updated_at=datetime.utcnow(),
            )
            db.add(pos)
        else:
            pos.quantity = qty
            pos.avg_cost = avg_cost
            pos.updated_at = datetime.utcnow()
        imported += 1

    await db.commit()
    return {
        "ok": True,
        "imported_positions": imported,
        "lines_with_errors": len(errors),
        "errors": errors[:20],
    }


@router.post("/positions", response_model=PositionOut)
async def upsert_position(
    payload: PositionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    ticker = payload.ticker.upper()
    stmt = select(PortfolioPosition).where(PortfolioPosition.user_id == user.id, PortfolioPosition.ticker == ticker)
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row is None:
        row = PortfolioPosition(
            user_id=user.id,
            ticker=ticker,
            quantity=payload.quantity,
            avg_cost=payload.avg_cost,
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    else:
        row.quantity = payload.quantity
        row.avg_cost = payload.avg_cost
        row.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(row)
    return PositionOut(id=row.id, ticker=row.ticker, quantity=row.quantity, avg_cost=row.avg_cost, updated_at=row.updated_at)


@router.delete("/positions/{position_id}")
async def delete_position(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    row = await db.get(PortfolioPosition, position_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Position not found")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.post("/orders")
async def place_order(
    payload: OrderIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    if settings.analytics_only_mode:
        raise HTTPException(status_code=410, detail="Trading routes are disabled in analytics-only mode.")

    ticker = payload.ticker.upper()
    side = payload.side.lower()
    if side not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="side must be buy/sell")

    latest = await state.stock_service.get_latest_quote(db, ticker)
    if latest is None:
        quote_payload = await state.market_data.get_quote(ticker)
        latest = await state.stock_service.save_quote(db, _normalize_quote_payload(ticker, quote_payload))

    result = await state.broker.execute(
        db=db,
        user=user,
        ticker=ticker,
        side=side,
        quantity=payload.quantity,
        order_type=payload.order_type,
        requested_price=payload.requested_price,
        market_price=latest.price,
    )

    response = {
        "id": result.id,
        "ticker": result.ticker,
        "side": result.side,
        "quantity": result.quantity,
        "filled_price": result.filled_price,
        "status": result.status,
        "created_at": result.created_at,
        "broker_mode": result.broker_mode,
        "broker_order_id": result.broker_order_id,
        "message": result.message,
    }

    if result.id is not None:
        created = await db.get(PaperOrder, result.id)
        if created:
            await _broadcast_order(user.id, created)
    return response


@router.get("/orders")
async def list_orders(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if settings.analytics_only_mode:
        raise HTTPException(status_code=410, detail="Trading routes are disabled in analytics-only mode.")
    stmt = select(PaperOrder).where(PaperOrder.user_id == user.id).order_by(PaperOrder.created_at.desc()).limit(100)
    rows = list((await db.execute(stmt)).scalars().all())
    return {
        "orders": [
            {
                "id": r.id,
                "ticker": r.ticker,
                "side": r.side,
                "quantity": r.quantity,
                "order_type": r.order_type,
                "requested_price": r.requested_price,
                "filled_price": r.filled_price,
                "status": r.status,
                "broker_mode": r.broker_mode,
                "broker_order_id": r.broker_order_id,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.get("/orders/{order_id}/status")
async def order_status(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if settings.analytics_only_mode:
        raise HTTPException(status_code=410, detail="Trading routes are disabled in analytics-only mode.")
    order = await db.get(PaperOrder, order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Order not found")

    data = await state.broker.order_status(db, user, order)
    await _broadcast_order(user.id, order)
    return {"id": order.id, "ticker": order.ticker, **data}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    if settings.analytics_only_mode:
        raise HTTPException(status_code=410, detail="Trading routes are disabled in analytics-only mode.")
    order = await db.get(PaperOrder, order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Order not found")

    data = await state.broker.cancel_order(db, user, order)
    await _broadcast_order(user.id, order)
    return {"id": order.id, "ticker": order.ticker, **data}


@router.post("/sync/positions")
async def sync_positions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "trader")),
):
    if settings.analytics_only_mode:
        raise HTTPException(status_code=410, detail="Broker sync is disabled in analytics-only mode.")
    data = await state.broker.sync_positions(db, user)
    return data
