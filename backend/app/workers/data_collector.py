import asyncio
from datetime import datetime, timedelta
from app.config import get_settings
from app.db.database import SessionLocal
from app.state import state


settings = get_settings()


async def collect_forever() -> None:
    retrain_every = timedelta(minutes=settings.model_retrain_minutes)
    next_retrain = datetime.utcnow()

    while True:
        tickers = sorted(state.watchlist) if state.watchlist else settings.ticker_list

        async with SessionLocal() as db:
            try:
                quote_payloads = await state.market_data.get_quotes(tickers)
            except Exception:
                quote_payloads = {}
            for ticker in tickers:
                quote = await state.stock_service.get_latest_quote(db, ticker)
                if quote is None:
                    try:
                        quote_payload = quote_payloads.get(ticker.upper()) or await state.market_data.get_quote(ticker)
                        quote_payload = {
                            "ticker": ticker.upper(),
                            "price": float(quote_payload.get("price") or 0.0),
                            "change_percent": float(quote_payload.get("change_percent") or 0.0),
                            "volume": int(float(quote_payload.get("volume") or 0)),
                            "open_price": float(quote_payload.get("open_price") or quote_payload.get("price") or 0.0),
                            "high_price": float(quote_payload.get("high_price") or quote_payload.get("price") or 0.0),
                            "low_price": float(quote_payload.get("low_price") or quote_payload.get("price") or 0.0),
                            "timestamp": quote_payload.get("timestamp") or datetime.utcnow(),
                            "source": str(quote_payload.get("source") or "provider_router"),
                            "is_live": True,
                        }
                        quote = await state.stock_service.save_quote(db, quote_payload)
                    except Exception:
                        continue

                try:
                    articles = await state.news_service.fetch_news(ticker)
                    if articles:
                        await state.news_service.save_articles(db, articles[:4])
                except Exception:
                    pass

                prediction = await state.ml_service.predict(db, ticker)

            if datetime.utcnow() >= next_retrain:
                for ticker in tickers:
                    await state.ml_service.train(db, ticker)
                next_retrain = datetime.utcnow() + retrain_every

        await asyncio.sleep(settings.update_interval_seconds)
