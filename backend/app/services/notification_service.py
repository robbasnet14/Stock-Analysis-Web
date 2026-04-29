import json
import smtplib
from email.message import EmailMessage
import httpx
from redis.asyncio import Redis
from app.config import get_settings


settings = get_settings()


class NotificationService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=15.0)
        self.redis: Redis | None = None

    def bind_redis(self, redis: Redis | None) -> None:
        self.redis = redis

    async def close(self) -> None:
        await self.client.aclose()

    async def send_telegram(self, chat_id: str, message: str) -> bool:
        if not settings.telegram_bot_token or not chat_id:
            return False

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        try:
            resp = await self.client.post(url, json=payload)
            return resp.status_code == 200
        except Exception:
            return False

    async def send_email(self, target: str, message: str, subject: str = "Stock Alert") -> bool:
        if not all([settings.smtp_host, settings.smtp_user, settings.smtp_password, settings.smtp_from, target]):
            return False

        try:
            email = EmailMessage()
            email["Subject"] = subject
            email["From"] = settings.smtp_from
            email["To"] = target
            email.set_content(message)
            email.add_alternative(f"<pre>{message}</pre>", subtype="html")

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(email)
            return True
        except Exception:
            return False

    async def send_webpush(self, target: str, message: str) -> bool:
        # Placeholder hook for web push provider integration.
        return bool(target and message)

    async def enqueue(self, channel: str, target: str, message: str, attempt: int = 0, subject: str = "Stock Alert") -> None:
        if self.redis is None:
            return
        payload = {"channel": channel, "target": target, "message": message, "attempt": attempt, "subject": subject}
        await self.redis.rpush("notification_queue", json.dumps(payload))

    async def process_once(self) -> bool:
        if self.redis is None:
            return False

        raw = await self.redis.lpop("notification_queue")
        if not raw:
            return False

        payload = json.loads(raw)
        channel = payload.get("channel", "")
        target = payload.get("target", "")
        message = payload.get("message", "")
        subject = payload.get("subject", "Stock Alert")
        attempt = int(payload.get("attempt", 0))

        ok = False
        if channel == "telegram":
            ok = await self.send_telegram(target, message)
        elif channel == "email":
            ok = await self.send_email(target, message, subject)
        elif channel == "webpush":
            ok = await self.send_webpush(target, message)

        if (not ok) and attempt < settings.notification_retry_max:
            await self.enqueue(channel, target, message, attempt + 1, subject=subject)

        return True
