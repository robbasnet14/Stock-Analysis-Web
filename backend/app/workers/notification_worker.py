import asyncio
from app.state import state


async def dispatch_notifications_forever() -> None:
    while True:
        processed = await state.notifications.process_once()
        if not processed:
            await asyncio.sleep(1.0)
