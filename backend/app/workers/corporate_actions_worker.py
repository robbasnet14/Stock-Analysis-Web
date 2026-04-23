import asyncio
from datetime import date, datetime, timedelta
from sqlalchemy import select
from app.config import get_settings
from app.db.database import SessionLocal
from app.models.corporate_action import DividendEvent, StockSplit, UserDividendCredit
from app.models.portfolio import PortfolioPosition
from app.state import state


settings = get_settings()


async def _fetch_splits(ticker: str) -> list[dict]:
    if not settings.finnhub_api_key:
        return []
    frm = (date.today() - timedelta(days=365 * 2)).isoformat()
    to = date.today().isoformat()
    url = "https://finnhub.io/api/v1/stock/split"
    resp = await state.stock_service.client.get(
        url,
        params={"symbol": ticker, "from": frm, "to": to, "token": settings.finnhub_api_key},
    )
    resp.raise_for_status()
    return resp.json()


async def _fetch_dividends(ticker: str) -> list[dict]:
    if not settings.finnhub_api_key:
        return []
    frm = (date.today() - timedelta(days=365 * 2)).isoformat()
    to = date.today().isoformat()
    url = "https://finnhub.io/api/v1/stock/dividend"
    resp = await state.stock_service.client.get(
        url,
        params={"symbol": ticker, "from": frm, "to": to, "token": settings.finnhub_api_key},
    )
    resp.raise_for_status()
    return resp.json()


async def process_corporate_actions_forever() -> None:
    while True:
        tickers = sorted(state.watchlist) if state.watchlist else settings.ticker_list
        async with SessionLocal() as db:
            for ticker in tickers:
                try:
                    splits = await _fetch_splits(ticker)
                except Exception:
                    splits = []
                for s in splits:
                    ex_date = s.get("date") or s.get("executionDate")
                    if not ex_date:
                        continue
                    try:
                        d = date.fromisoformat(str(ex_date)[:10])
                    except Exception:
                        continue
                    from_factor = float(s.get("fromFactor") or s.get("from") or 1.0)
                    to_factor = float(s.get("toFactor") or s.get("to") or 1.0)
                    if from_factor <= 0 or to_factor <= 0:
                        continue
                    stmt = select(StockSplit).where(
                        StockSplit.ticker == ticker,
                        StockSplit.effective_date == d,
                        StockSplit.from_factor == from_factor,
                        StockSplit.to_factor == to_factor,
                    )
                    row = (await db.execute(stmt)).scalar_one_or_none()
                    if row is None:
                        db.add(
                            StockSplit(
                                ticker=ticker,
                                effective_date=d,
                                from_factor=from_factor,
                                to_factor=to_factor,
                                applied=False,
                            )
                        )

                try:
                    dividends = await _fetch_dividends(ticker)
                except Exception:
                    dividends = []
                for dv in dividends:
                    pay = dv.get("paymentDate") or dv.get("payDate")
                    ex = dv.get("date") or dv.get("exDate")
                    if not pay:
                        continue
                    try:
                        pay_date = date.fromisoformat(str(pay)[:10])
                    except Exception:
                        continue
                    ex_date = None
                    if ex:
                        try:
                            ex_date = date.fromisoformat(str(ex)[:10])
                        except Exception:
                            ex_date = None
                    cash = float(dv.get("amount") or dv.get("cashAmount") or 0.0)
                    stmt = select(DividendEvent).where(
                        DividendEvent.ticker == ticker,
                        DividendEvent.pay_date == pay_date,
                        DividendEvent.cash_amount == cash,
                    )
                    row = (await db.execute(stmt)).scalar_one_or_none()
                    if row is None:
                        db.add(
                            DividendEvent(
                                ticker=ticker,
                                ex_date=ex_date,
                                pay_date=pay_date,
                                cash_amount=cash,
                                applied=False,
                            )
                        )

            await db.commit()

            # Apply unapplied splits to all positions.
            split_rows = list((await db.execute(select(StockSplit).where(StockSplit.applied == False))).scalars().all())  # noqa: E712
            for split in split_rows:
                ratio = split.to_factor / split.from_factor
                if ratio <= 0:
                    split.applied = True
                    continue
                positions = list((await db.execute(select(PortfolioPosition).where(PortfolioPosition.ticker == split.ticker))).scalars().all())
                for pos in positions:
                    pos.quantity = float(pos.quantity) * ratio
                    pos.avg_cost = float(pos.avg_cost) / ratio if ratio else float(pos.avg_cost)
                    pos.updated_at = datetime.utcnow()
                split.applied = True
            await db.commit()

            # Apply dividends as user credits.
            dividend_rows = list((await db.execute(select(DividendEvent).where(DividendEvent.applied == False))).scalars().all())  # noqa: E712
            for dv in dividend_rows:
                positions = list((await db.execute(select(PortfolioPosition).where(PortfolioPosition.ticker == dv.ticker))).scalars().all())
                for pos in positions:
                    stmt = select(UserDividendCredit).where(
                        UserDividendCredit.user_id == pos.user_id,
                        UserDividendCredit.ticker == dv.ticker,
                        UserDividendCredit.pay_date == dv.pay_date,
                    )
                    existing = (await db.execute(stmt)).scalar_one_or_none()
                    if existing is not None:
                        continue
                    amount = float(pos.quantity) * float(dv.cash_amount)
                    db.add(
                        UserDividendCredit(
                            user_id=pos.user_id,
                            ticker=dv.ticker,
                            pay_date=dv.pay_date,
                            amount=amount,
                        )
                    )
                dv.applied = True
            await db.commit()

        await asyncio.sleep(60 * 30)
