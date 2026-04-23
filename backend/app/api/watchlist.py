import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_current_user
from app.models.stock import StockPrice
from app.models.symbol import SymbolMaster
from app.models.user import User
from app.models.watchlist import Watchlist
from app.schemas.watchlist import WatchlistAddIn, WatchlistItemOut, WatchlistMutationOut
from app.state import state


router = APIRouter(prefix="/watchlist", tags=["watchlist"])


async def _list_rows(db: AsyncSession, user_id: int) -> list[Watchlist]:
    stmt = select(Watchlist).where(Watchlist.user_id == user_id).order_by(Watchlist.symbol.asc())
    rows = list((await db.execute(stmt)).scalars().all())
    return rows


@router.get("", response_model=list[WatchlistItemOut])
async def get_watchlist(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WatchlistItemOut]:
    rows = await _list_rows(db, user.id)
    if not rows:
        return []

    symbols = [r.symbol for r in rows]

    symbol_stmt = select(SymbolMaster).where(SymbolMaster.symbol.in_(symbols))
    symbol_map = {s.symbol: s for s in (await db.execute(symbol_stmt)).scalars().all()}

    # Fetch latest DB rows in a single query, then keep the newest row per ticker.
    latest_stmt = (
        select(StockPrice)
        .where(StockPrice.ticker.in_(symbols))
        .order_by(StockPrice.ticker.asc(), StockPrice.timestamp.desc())
    )
    latest_rows = list((await db.execute(latest_stmt)).scalars().all())
    latest_map: dict[str, StockPrice] = {}
    for row in latest_rows:
        if row.ticker not in latest_map:
            latest_map[row.ticker] = row

    out: list[WatchlistItemOut] = []
    for item in rows:
        symbol = item.symbol
        meta = symbol_map.get(symbol)
        latest = latest_map.get(symbol)

        price: float = float(latest.price) if latest is not None else 0.0
        percent: float = float(latest.change_percent) if latest is not None else 0.0
        if state.redis is not None:
            cached = await state.redis.get(f"price:{symbol}")
            if cached:
                try:
                    price = float(cached)
                except ValueError:
                    pass
            else:
                cached_latest = await state.redis.get(f"latest:{symbol}")
                if cached_latest:
                    try:
                        payload = json.loads(cached_latest)
                        price = float(payload.get("price", price))
                        if latest is None:
                            percent = float(payload.get("change_percent", 0.0))
                    except Exception:
                        pass

        change = price * (percent / 100.0) if price else 0.0
        out.append(
            WatchlistItemOut(
                symbol=symbol,
                name=meta.name if meta is not None and meta.name else symbol,
                price=round(price, 6),
                change=round(change, 6),
                percent=round(percent, 6),
                created_at=item.created_at,
            )
        )
    return out


@router.post("/add", response_model=WatchlistMutationOut)
async def add_watchlist(
    payload: WatchlistAddIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchlistMutationOut:
    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    symbol_row = await db.get(SymbolMaster, symbol)
    if symbol_row is None:
        # Auto-onboard valid live symbols so users can add real holdings
        # even when symbol master has not been fully synced yet.
        try:
            await state.market_data.get_quote(symbol)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"symbol {symbol} not found ({exc})") from exc

        symbol_row = SymbolMaster(
            symbol=symbol,
            name=symbol,
            exchange="US",
            type="Common Stock",
            display_symbol=symbol,
            currency="USD",
            mic="",
            updated_at=datetime.utcnow(),
        )
        db.add(symbol_row)
        await db.flush()

    db.add(Watchlist(user_id=user.id, symbol=symbol))
    try:
        await db.commit()
    except IntegrityError:
        # Duplicate adds are intentionally idempotent.
        await db.rollback()

    state.watchlist.add(symbol)
    return WatchlistMutationOut(status="added", symbol=symbol)


@router.delete("/remove/{symbol}", response_model=WatchlistMutationOut)
async def remove_watchlist(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchlistMutationOut:
    sym = symbol.strip().upper()
    stmt = select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.symbol == sym)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return WatchlistMutationOut(status="removed", symbol=sym)


@router.delete("/remove", response_model=WatchlistMutationOut, include_in_schema=False)
async def remove_watchlist_legacy(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchlistMutationOut:
    return await remove_watchlist(symbol=symbol, db=db, user=user)


@router.get("/intelligence")
async def watchlist_intelligence(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows = await _list_rows(db, user.id)
    symbols = [r.symbol for r in rows]
    if not symbols:
        return {"items": [], "as_of": None}
    items = await state.stock_service.get_watchlist_intelligence(db, symbols)
    return {"items": items}
