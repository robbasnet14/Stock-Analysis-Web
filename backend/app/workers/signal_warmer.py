import asyncio
from app.config import get_settings
from app.db.database import SessionLocal
from app.state import state


settings = get_settings()


async def warm_signals_forever() -> None:
    while True:
        tickers = sorted(state.watchlist) if state.watchlist else settings.ticker_list
        async with SessionLocal() as db:
            for ticker in tickers:
                try:
                    await state.ml_service.predict(db, ticker)
                except Exception:
                    pass
        await asyncio.sleep(45)
