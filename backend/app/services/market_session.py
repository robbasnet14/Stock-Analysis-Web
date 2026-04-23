from datetime import datetime
from zoneinfo import ZoneInfo


NY_TZ = ZoneInfo("America/New_York")


def get_market_session(now: datetime | None = None) -> dict:
    current = now.astimezone(NY_TZ) if now is not None else datetime.now(NY_TZ)
    hhmm = current.hour * 100 + current.minute
    weekday = current.weekday()  # Monday=0

    if weekday >= 5:
        session = "closed"
    elif 400 <= hhmm < 930:
        session = "premarket"
    elif 930 <= hhmm < 1600:
        session = "market"
    elif 1600 <= hhmm < 2000:
        session = "after-hours"
    else:
        session = "closed"

    is_open = session in {"premarket", "market", "after-hours"}
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return {"session": session, "is_open": is_open, "timestamp": timestamp}
