from __future__ import annotations

from datetime import datetime
from typing import Any
import httpx
from xml.etree import ElementTree as ET


class NewsRssProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def yahoo(self, symbol: str) -> list[dict[str, Any]]:
        url = f"https://finance.yahoo.com/rss/headline?s={symbol.upper()}"
        return await self._parse_rss(url, source="yahoo_rss", symbol=symbol)

    async def google(self, query: str) -> list[dict[str, Any]]:
        q = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={q}+stock"
        return await self._parse_rss(url, source="google_rss", symbol=query)

    async def _parse_rss(self, url: str, source: str, symbol: str) -> list[dict[str, Any]]:
        resp = await self.client.get(url)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        out: list[dict[str, Any]] = []
        for item in root.findall(".//item")[:30]:
            out.append(
                {
                    "ticker": symbol.upper(),
                    "headline": (item.findtext("title") or "").strip(),
                    "summary": (item.findtext("description") or "").strip(),
                    "source": source,
                    "url": (item.findtext("link") or "").strip(),
                    "published_at": datetime.utcnow(),
                }
            )
        return out
