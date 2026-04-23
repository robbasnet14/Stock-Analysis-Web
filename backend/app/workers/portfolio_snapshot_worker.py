import asyncio
from datetime import datetime
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.portfolio import PortfolioPosition
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.user import User
from app.state import state


async def snapshot_portfolios_forever() -> None:
    while True:
        async with SessionLocal() as db:
            users = list((await db.execute(select(User))).scalars().all())
            for user in users:
                positions = list((await db.execute(select(PortfolioPosition).where(PortfolioPosition.user_id == user.id))).scalars().all())
                if not positions:
                    continue

                total_value = 0.0
                for pos in positions:
                    price = 0.0
                    if state.redis is not None:
                        cached = await state.redis.get(f"price:{pos.ticker}")
                        if cached:
                            try:
                                price = float(cached)
                            except Exception:
                                price = 0.0
                    if price <= 0:
                        latest = await state.stock_service.get_latest_quote(db, pos.ticker)
                        if latest:
                            price = float(latest.price)
                    total_value += float(pos.quantity) * price

                db.add(PortfolioSnapshot(user_id=user.id, timestamp=datetime.utcnow(), value=total_value))
            await db.commit()
        await asyncio.sleep(60.0)
