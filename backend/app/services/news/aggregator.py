from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx

from app.config import get_settings

settings = get_settings()


def _parse_dt(text: str | None) -> datetime:
    if not text:
        return datetime.now(timezone.utc)
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class NewsAggregator:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch_finnhub(self, symbol: str) -> list[dict[str, Any]]:
        if not settings.finnhub_api_key:
            return []
        to_d = datetime.utcnow().date().isoformat()
        from_d = (datetime.utcnow().date() - timedelta(days=3)).isoformat()
        resp = await self.client.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": symbol.upper(), "from": from_d, "to": to_d, "token": settings.finnhub_api_key},
        )
        resp.raise_for_status()
        rows = []
        for item in (resp.json() or [])[:50]:
            rows.append(
                {
                    "ticker": symbol.upper(),
                    "title": str(item.get("headline") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "url": str(item.get("url") or "").strip(),
                    "source": str(item.get("source") or "finnhub"),
                    "published_at": datetime.fromtimestamp(int(item.get("datetime", 0) or 0), tz=timezone.utc)
                    if item.get("datetime")
                    else datetime.now(timezone.utc),
                }
            )
        return [r for r in rows if r["title"]]

    async def _fetch_rss(self, url: str, ticker: str, source: str) -> list[dict[str, Any]]:
        resp = await self.client.get(url)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        rows: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub = _parse_dt(item.findtext("pubDate"))
            if not title:
                continue
            rows.append(
                {
                    "ticker": ticker.upper(),
                    "title": title,
                    "summary": desc,
                    "url": link,
                    "source": source,
                    "published_at": pub,
                }
            )
        return rows

    async def fetch_yahoo(self, symbol: str) -> list[dict[str, Any]]:
        return await self._fetch_rss(f"https://finance.yahoo.com/rss/headline?s={quote_plus(symbol.upper())}", symbol, "yahoo")

    async def fetch_google_news(self, symbol: str) -> list[dict[str, Any]]:
        q = quote_plus(f"{symbol.upper()} stock")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        return await self._fetch_rss(url, symbol, "google_news")

    async def fetch_marketaux(self, symbols: list[str]) -> list[dict[str, Any]]:
        if not settings.marketaux_api_key or not symbols:
            return []
        resp = await self.client.get(
            "https://api.marketaux.com/v1/news/all",
            params={
                "api_token": settings.marketaux_api_key,
                "symbols": ",".join(symbols[:3]),
                "language": "en",
                "limit": 50,
            },
        )
        resp.raise_for_status()
        rows = []
        for item in (resp.json() or {}).get("data", [])[:50]:
            entities = item.get("entities") or []
            tags = [str(e.get("symbol") or "").upper() for e in entities if e.get("symbol")]
            for t in (tags or symbols[:1]):
                rows.append(
                    {
                        "ticker": t,
                        "title": str(item.get("title") or "").strip(),
                        "summary": str(item.get("description") or "").strip(),
                        "url": str(item.get("url") or "").strip(),
                        "source": "marketaux",
                        "published_at": _parse_dt(str(item.get("published_at") or "")),
                    }
                )
        return [r for r in rows if r["title"]]

    async def fetch_alpha_vantage_news(self, symbols: list[str]) -> list[dict[str, Any]]:
        if not settings.alpha_vantage_api_key or not settings.alphavantage_news_enabled or not symbols:
            return []
        resp = await self.client.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": ",".join(symbols[:3]),
                "apikey": settings.alpha_vantage_api_key,
                "limit": 50,
            },
        )
        resp.raise_for_status()
        rows: list[dict[str, Any]] = []
        for item in (resp.json() or {}).get("feed", [])[:50]:
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            url = str(item.get("url") or "").strip()
            pub = _parse_dt(str(item.get("time_published") or ""))
            ticker_sent = item.get("ticker_sentiment") or []
            tags = [str(t.get("ticker") or "").upper() for t in ticker_sent if t.get("ticker")]
            for t in (tags or symbols[:1]):
                rows.append(
                    {
                        "ticker": t,
                        "title": title,
                        "summary": summary,
                        "url": url,
                        "source": "alpha_vantage",
                        "published_at": pub,
                    }
                )
        return [r for r in rows if r["title"]]

