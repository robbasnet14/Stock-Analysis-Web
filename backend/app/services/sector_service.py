from __future__ import annotations

import json
from datetime import datetime, timedelta
import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.symbol_fundamental import SymbolFundamental
from app.models.symbol import SymbolMaster
from app.services.stock_service import StockService

settings = get_settings()


class SectorService:
    def __init__(self, stock_service: StockService) -> None:
        self.stock_service = stock_service
        self.client = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _normalize(values: list[float], value: float) -> float:
        if not values:
            return 0.5
        lo = float(min(values))
        hi = float(max(values))
        if hi - lo < 1e-9:
            return 0.5
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))

    @staticmethod
    def _infer_sector(symbol: str, name: str) -> str:
        symbol = symbol.upper()
        name_l = (name or "").lower()
        if symbol in {"NVDA", "AMD", "TSM", "SMCI", "AVGO", "QCOM"}:
            return "semiconductors"
        if any(k in name_l for k in ["software", "technology", "tech", "cloud", "internet", "platform"]):
            return "technology"
        if any(k in name_l for k in ["energy", "oil", "gas", "petroleum"]):
            return "energy"
        if any(k in name_l for k in ["bank", "financial", "insurance", "capital"]):
            return "financials"
        if any(k in name_l for k in ["health", "pharma", "biotech", "medical"]):
            return "healthcare"
        if any(k in name_l for k in ["retail", "consumer", "ecommerce", "apparel"]):
            return "consumer"
        return "other"

    async def _fetch_provider_sector(self, symbol: str) -> tuple[str, str] | None:
        if not settings.finnhub_api_key:
            return None
        url = "https://finnhub.io/api/v1/stock/profile2"
        try:
            resp = await self.client.get(
                url,
                params={"symbol": symbol.upper(), "token": settings.finnhub_api_key},
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
            sector = str(data.get("finnhubIndustry") or "").strip()
            industry = str(data.get("finnhubIndustry") or "").strip()
            if not sector:
                return None
            return sector.lower(), industry.lower()
        except Exception:
            return None

    async def _sector_for_symbol(self, db: AsyncSession, ticker: str) -> str:
        symbol = ticker.upper()
        row = (await db.execute(select(SymbolFundamental).where(SymbolFundamental.symbol == symbol))).scalar_one_or_none()
        stale = False
        if row is not None:
            stale = row.updated_at < (datetime.utcnow() - timedelta(days=14))
            if row.sector and not stale:
                return row.sector

        provider_sector = await self._fetch_provider_sector(symbol)
        if provider_sector is not None:
            sector, industry = provider_sector
            if row is None:
                row = SymbolFundamental(symbol=symbol, sector=sector, industry=industry, provider="finnhub", updated_at=datetime.utcnow())
                db.add(row)
            else:
                row.sector = sector
                row.industry = industry
                row.provider = "finnhub"
                row.updated_at = datetime.utcnow()
            await db.commit()
            return sector

        symbol_row = await db.get(SymbolMaster, symbol)
        name = symbol_row.name if symbol_row else symbol
        fallback = self._infer_sector(symbol, name)
        if row is None:
            db.add(SymbolFundamental(symbol=symbol, sector=fallback, industry=fallback, provider="heuristic", updated_at=datetime.utcnow()))
        else:
            row.sector = fallback
            row.industry = fallback
            row.provider = "heuristic"
            row.updated_at = datetime.utcnow()
        await db.commit()
        return fallback

    async def get_sector_strength(self, db: AsyncSession, tickers: list[str], redis_client=None) -> dict:
        cache_key = "market:sectors:v1"
        if redis_client is not None:
            cached = await redis_client.get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        sectors: dict[str, list[dict]] = {}
        for ticker in sorted(set(tickers))[:120]:
            sector = await self._sector_for_symbol(db, ticker)
            rows = await self.stock_service.get_price_history(db, ticker, limit=40)
            if len(rows) < 22:
                continue
            p_last = float(rows[-1].price)
            ret5 = ((p_last / float(rows[-6].price)) - 1.0) * 100.0 if rows[-6].price else 0.0
            ret20 = ((p_last / float(rows[-21].price)) - 1.0) * 100.0 if rows[-21].price else 0.0
            vols = [float(r.volume) for r in rows[-31:]]
            avg_30 = float(np.mean(vols[:-1])) if len(vols) > 1 else float(np.mean(vols))
            vol_strength = (vols[-1] / avg_30) if avg_30 > 0 else 1.0
            sectors.setdefault(sector, []).append(
                {"ret5": ret5, "ret20": ret20, "volume_strength": vol_strength}
            )

        temp_rows: list[dict] = []
        raw_scores: list[float] = []
        for sector, items in sectors.items():
            avg_return_5d = float(np.mean([i["ret5"] for i in items]))
            avg_return_20d = float(np.mean([i["ret20"] for i in items]))
            volume_strength = float(np.mean([i["volume_strength"] for i in items]))
            raw_score = 0.45 * avg_return_5d + 0.4 * avg_return_20d + 0.15 * ((volume_strength - 1.0) * 20.0)
            raw_scores.append(raw_score)
            temp_rows.append(
                {
                    "sector": sector,
                    "raw_score": raw_score,
                    "avg_return_5d": avg_return_5d,
                    "avg_return_20d": avg_return_20d,
                    "volume_strength": volume_strength,
                }
            )

        output = []
        for row in temp_rows:
            strength = self._normalize(raw_scores, row["raw_score"])
            output.append(
                {
                    "sector": row["sector"],
                    "strength": round(strength, 4),
                    "avg_return_5d": round(row["avg_return_5d"], 4),
                    "avg_return_20d": round(row["avg_return_20d"], 4),
                    "volume_strength": round(row["volume_strength"], 4),
                }
            )

        output.sort(key=lambda x: x["strength"], reverse=True)
        payload = {"as_of": datetime.utcnow().isoformat(), "items": output}
        if redis_client is not None:
            await redis_client.set(cache_key, json.dumps(payload), ex=300)
        return payload
