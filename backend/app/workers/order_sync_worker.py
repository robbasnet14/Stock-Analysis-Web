import asyncio
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.portfolio import PaperOrder
from app.models.user import User
from app.state import state


PENDING_STATUSES = {
    "new",
    "accepted",
    "pending_new",
    "partially_filled",
    "pending_replace",
    "replaced",
    "accepted_for_bidding",
    "stopped",
    "calculated",
    "submitted",
}


async def sync_orders_forever() -> None:
    while True:
        async with SessionLocal() as db:
            stmt = select(PaperOrder).where(PaperOrder.status.in_(PENDING_STATUSES)).order_by(PaperOrder.created_at.desc()).limit(200)
            orders = list((await db.execute(stmt)).scalars().all())

            for order in orders:
                user = await db.get(User, order.user_id)
                if user is None:
                    continue

                old_status = order.status
                old_price = order.filled_price
                status_data = await state.broker.order_status(db, user, order)

                changed = status_data.get("status") != old_status or float(status_data.get("filled_price", old_price)) != float(old_price)
                if not changed:
                    continue

                await state.order_websocket.broadcast(
                    order.user_id,
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

        await asyncio.sleep(5.0)
