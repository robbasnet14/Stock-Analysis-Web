from __future__ import annotations

from datetime import datetime
import httpx
from app.config import get_settings


settings = get_settings()


class LLMService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def explain_stock(
        self,
        *,
        ticker: str,
        horizon: str,
        bull_probability: float,
        reasons: list[str],
        sentiment: float,
        momentum_pct: float,
        volume_ratio: float,
    ) -> str:
        ticker = ticker.upper()
        tone = "bullish" if bull_probability >= 0.6 else "bearish" if bull_probability <= 0.4 else "mixed"
        fallback = (
            f"{ticker} looks {tone} for {horizon} horizon. "
            f"Bull probability is {round(bull_probability * 100, 1)}%. "
            f"Momentum is {momentum_pct:.2f}% with volume ratio {volume_ratio:.2f}x and sentiment {sentiment:.2f}. "
            f"Key drivers: {', '.join(reasons) if reasons else 'mixed indicators'}."
        )

        if not settings.openai_api_key:
            return fallback

        prompt = (
            "You are an investment analytics assistant. "
            "Write a concise, plain-English explanation (4 bullet points max) based only on provided signals. "
            "Do not provide financial advice.\n"
            f"Ticker: {ticker}\n"
            f"Horizon: {horizon}\n"
            f"Bull probability: {bull_probability:.4f}\n"
            f"Sentiment score: {sentiment:.4f}\n"
            f"Momentum percent: {momentum_pct:.4f}\n"
            f"Volume ratio: {volume_ratio:.4f}\n"
            f"Reasons: {', '.join(reasons)}\n"
            f"As-of: {datetime.utcnow().isoformat()}Z"
        )

        try:
            resp = await self.client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "input": prompt,
                    "temperature": 0.2,
                    "max_output_tokens": 220,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            text = (payload.get("output_text") or "").strip()
            return text or fallback
        except Exception:
            return fallback
