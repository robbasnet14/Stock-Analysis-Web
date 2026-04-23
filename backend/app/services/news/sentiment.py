from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

try:
    from nltk.sentiment import SentimentIntensityAnalyzer
except Exception:  # pragma: no cover
    SentimentIntensityAnalyzer = None


class NewsSentimentService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=25.0)
        self.vader = SentimentIntensityAnalyzer() if SentimentIntensityAnalyzer is not None else None
        self.batch_size = max(1, int(settings.openai_sentiment_batch_size or 10))
        self.daily_cap = float(os.getenv("OPENAI_DAILY_SPEND_CAP_USD", "2.0"))

    async def close(self) -> None:
        await self.client.aclose()

    def _vader(self, text: str) -> tuple[str, float]:
        if self.vader is None:
            t = (text or "").lower()
            pos = sum(1 for w in ("beat", "surge", "strong", "upgrade", "growth", "bullish") if w in t)
            neg = sum(1 for w in ("miss", "drop", "weak", "downgrade", "bearish", "lawsuit") if w in t)
            compound = max(-1.0, min(1.0, (pos - neg) / 5.0))
        else:
            compound = float(self.vader.polarity_scores(text or "").get("compound", 0.0))
        if compound >= 0.2:
            return "bullish", compound
        if compound <= -0.2:
            return "bearish", compound
        return "neutral", compound

    async def _can_spend(self, redis_client) -> bool:
        if redis_client is None or not settings.openai_api_key:
            return False
        day_key = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"news:openai:spend:{day_key}"
        current = float(await redis_client.get(key) or 0.0)
        return current < self.daily_cap

    async def _mark_spend(self, redis_client, usd: float) -> None:
        if redis_client is None:
            return
        day_key = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"news:openai:spend:{day_key}"
        await redis_client.incrbyfloat(key, float(max(0.0, usd)))
        await redis_client.expire(key, 172800)

    async def _openai_batch(self, rows: list[dict[str, Any]]) -> list[tuple[str, float]]:
        prompt_items = [
            {
                "idx": i,
                "text": f"{(r.get('title') or '').strip()} {(r.get('summary') or '').strip()}",
            }
            for i, r in enumerate(rows)
        ]
        body = {
            "model": settings.openai_model or "gpt-4o-mini",
            "input": (
                "Classify each finance headline sentiment as bullish, bearish, or neutral. "
                "Return strict JSON list with objects: idx, label, score in [-1,1].\n"
                f"Items: {json.dumps(prompt_items)}"
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "news_sentiment_batch",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "idx": {"type": "integer"},
                                        "label": {"type": "string"},
                                        "score": {"type": "number"},
                                    },
                                    "required": ["idx", "label", "score"],
                                },
                            }
                        },
                        "required": ["items"],
                    },
                }
            },
            "max_output_tokens": 400,
            "temperature": 0.0,
        }
        resp = await self.client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
        text = payload.get("output_text") or "{}"
        parsed = json.loads(text)
        out = [("neutral", 0.0)] * len(rows)
        for item in parsed.get("items", []):
            idx = int(item.get("idx", -1))
            if 0 <= idx < len(rows):
                label = str(item.get("label", "neutral")).lower()
                if label not in {"bullish", "bearish", "neutral"}:
                    label = "neutral"
                score = float(item.get("score", 0.0))
                out[idx] = (label, max(-1.0, min(1.0, score)))
        return out

    async def score_articles(self, rows: list[dict[str, Any]], redis_client=None) -> list[dict[str, Any]]:
        if not rows:
            return rows

        # Stage 1: VADER pre-score.
        results: list[dict[str, Any]] = []
        ambiguous: list[int] = []
        for i, row in enumerate(rows):
            label, score = self._vader(f"{row.get('title') or ''}. {row.get('summary') or ''}")
            row["sentiment_label"] = label
            row["sentiment_score"] = round(float(score), 6)
            row["sentiment_model"] = "vader"
            results.append(row)
            if abs(score) < 0.15:
                ambiguous.append(i)

        # Stage 2: OpenAI escalation for ambiguous headlines only.
        if settings.openai_api_key and ambiguous and await self._can_spend(redis_client):
            for i in range(0, len(ambiguous), self.batch_size):
                idxs = ambiguous[i : i + self.batch_size]
                batch_rows = [results[j] for j in idxs]
                try:
                    scored = await self._openai_batch(batch_rows)
                except Exception:
                    continue
                # Approximate tiny cost for budgeting (keeps cap functional).
                await self._mark_spend(redis_client, 0.002 * len(batch_rows))
                for local_idx, (label, score) in enumerate(scored):
                    global_idx = idxs[local_idx]
                    results[global_idx]["sentiment_label"] = label
                    results[global_idx]["sentiment_score"] = round(float(score), 6)
                    results[global_idx]["sentiment_model"] = "gpt-4o-mini"

        return results

