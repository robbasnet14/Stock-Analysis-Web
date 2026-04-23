from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.portfolio import PaperOrder, PortfolioPosition
from app.models.user import User


settings = get_settings()


@dataclass
class ExecResult:
    id: int | None
    ticker: str
    side: str
    quantity: float
    filled_price: float
    status: str
    created_at: datetime
    broker_mode: str
    broker_order_id: str = ""
    message: str = ""


class BrokerAdapter(ABC):
    mode: str = "base"

    @abstractmethod
    async def execute_order(
        self,
        db: AsyncSession,
        user: User,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str,
        requested_price: float | None,
        market_price: float,
    ) -> ExecResult:
        raise NotImplementedError

    async def get_order_status(self, db: AsyncSession, user: User, order: PaperOrder) -> dict:
        return {
            "status": order.status,
            "filled_price": order.filled_price,
            "broker_order_id": order.broker_order_id,
            "broker_mode": order.broker_mode,
        }

    async def cancel_order(self, db: AsyncSession, user: User, order: PaperOrder) -> dict:
        if order.status not in {"filled", "canceled"}:
            order.status = "canceled"
            await db.commit()
        return {"ok": True, "status": order.status, "broker_mode": order.broker_mode}

    async def sync_positions(self, db: AsyncSession, user: User) -> dict:
        return {"synced": 0, "broker_mode": self.mode, "message": "No external sync for this adapter"}

    async def account_summary(self, db: AsyncSession, user: User) -> dict:
        return {"broker_mode": self.mode, "message": "No external account summary for this adapter"}


class PaperBrokerAdapter(BrokerAdapter):
    mode = "paper"

    async def execute_order(
        self,
        db: AsyncSession,
        user: User,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str,
        requested_price: float | None,
        market_price: float,
    ) -> ExecResult:
        fill_price = market_price if order_type == "market" else (requested_price or market_price)

        order = PaperOrder(
            user_id=user.id,
            ticker=ticker,
            side=side,
            order_type=order_type,
            quantity=quantity,
            requested_price=requested_price or 0.0,
            filled_price=fill_price,
            status="filled",
            broker_mode=self.mode,
            broker_order_id="",
        )
        db.add(order)

        stmt = select(PortfolioPosition).where(PortfolioPosition.user_id == user.id, PortfolioPosition.ticker == ticker)
        pos = (await db.execute(stmt)).scalar_one_or_none()

        qty_delta = quantity if side == "buy" else -quantity
        if pos is None:
            if qty_delta < 0:
                return ExecResult(
                    id=None,
                    ticker=ticker,
                    side=side,
                    quantity=quantity,
                    filled_price=0.0,
                    status="rejected",
                    created_at=datetime.utcnow(),
                    broker_mode=self.mode,
                    message="Cannot sell non-existing position",
                )
            pos = PortfolioPosition(user_id=user.id, ticker=ticker, quantity=qty_delta, avg_cost=fill_price, updated_at=datetime.utcnow())
            db.add(pos)
        else:
            if side == "buy":
                total_cost = pos.avg_cost * pos.quantity + fill_price * quantity
                total_qty = pos.quantity + quantity
                pos.quantity = total_qty
                pos.avg_cost = total_cost / total_qty if total_qty else 0.0
            else:
                pos.quantity = max(0.0, pos.quantity - quantity)
            pos.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(order)

        return ExecResult(
            id=order.id,
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            filled_price=order.filled_price,
            status=order.status,
            created_at=order.created_at,
            broker_mode=self.mode,
            broker_order_id=order.broker_order_id,
        )

    async def account_summary(self, db: AsyncSession, user: User) -> dict:
        stmt = select(PortfolioPosition).where(PortfolioPosition.user_id == user.id)
        positions = list((await db.execute(stmt)).scalars().all())

        market_value = sum(p.quantity * p.avg_cost for p in positions)
        equity = 100_000 + market_value
        buying_power = max(0.0, 200_000 - market_value)
        return {
            "broker_mode": self.mode,
            "equity": round(equity, 2),
            "buying_power": round(buying_power, 2),
            "cash": 100_000.0,
            "positions_count": len(positions),
        }


class AlpacaBrokerAdapter(BrokerAdapter):
    mode = "alpaca"

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self.client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
            "Content-Type": "application/json",
        }

    def _configured(self) -> bool:
        return bool(settings.alpaca_api_key and settings.alpaca_secret_key and settings.alpaca_base_url)

    async def execute_order(
        self,
        db: AsyncSession,
        user: User,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str,
        requested_price: float | None,
        market_price: float,
    ) -> ExecResult:
        if not self._configured():
            return ExecResult(
                id=None,
                ticker=ticker,
                side=side,
                quantity=quantity,
                filled_price=0.0,
                status="pending_adapter",
                created_at=datetime.utcnow(),
                broker_mode=self.mode,
                message="Set ALPACA_API_KEY / ALPACA_SECRET_KEY / ALPACA_BASE_URL to enable live Alpaca execution.",
            )

        payload: dict = {
            "symbol": ticker,
            "qty": str(quantity),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
        }

        if order_type == "limit":
            payload["limit_price"] = str(requested_price or market_price)

        try:
            url = f"{settings.alpaca_base_url.rstrip('/')}/v2/orders"
            resp = await self.client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 300:
                return ExecResult(
                    id=None,
                    ticker=ticker,
                    side=side,
                    quantity=quantity,
                    filled_price=0.0,
                    status="rejected",
                    created_at=datetime.utcnow(),
                    broker_mode=self.mode,
                    message=f"Alpaca rejected order: {resp.text}",
                )

            order_data = resp.json()
            alpaca_id = str(order_data.get("id", ""))
            status = str(order_data.get("status", "submitted"))
            filled_avg_price = float(order_data.get("filled_avg_price") or 0.0)
            created_at = datetime.utcnow()

            local_order = PaperOrder(
                user_id=user.id,
                ticker=ticker,
                side=side,
                order_type=order_type,
                quantity=quantity,
                requested_price=float(requested_price or 0.0),
                filled_price=filled_avg_price,
                status=status,
                broker_mode=self.mode,
                broker_order_id=alpaca_id,
            )
            db.add(local_order)
            await db.commit()
            await db.refresh(local_order)

            return ExecResult(
                id=local_order.id,
                ticker=ticker,
                side=side,
                quantity=quantity,
                filled_price=local_order.filled_price,
                status=local_order.status,
                created_at=local_order.created_at,
                broker_mode=self.mode,
                broker_order_id=alpaca_id,
            )
        except Exception as exc:
            return ExecResult(
                id=None,
                ticker=ticker,
                side=side,
                quantity=quantity,
                filled_price=0.0,
                status="error",
                created_at=datetime.utcnow(),
                broker_mode=self.mode,
                message=f"Alpaca execution error: {exc}",
            )

    async def get_order_status(self, db: AsyncSession, user: User, order: PaperOrder) -> dict:
        if not self._configured() or not order.broker_order_id:
            return await super().get_order_status(db, user, order)

        url = f"{settings.alpaca_base_url.rstrip('/')}/v2/orders/{order.broker_order_id}"
        resp = await self.client.get(url, headers=self._headers())
        if resp.status_code >= 300:
            return {
                "status": order.status,
                "filled_price": order.filled_price,
                "broker_order_id": order.broker_order_id,
                "broker_mode": order.broker_mode,
                "message": resp.text,
            }

        data = resp.json()
        order.status = str(data.get("status", order.status))
        order.filled_price = float(data.get("filled_avg_price") or order.filled_price)
        await db.commit()

        return {
            "status": order.status,
            "filled_price": order.filled_price,
            "broker_order_id": order.broker_order_id,
            "broker_mode": order.broker_mode,
        }

    async def cancel_order(self, db: AsyncSession, user: User, order: PaperOrder) -> dict:
        if not self._configured() or not order.broker_order_id:
            return await super().cancel_order(db, user, order)

        url = f"{settings.alpaca_base_url.rstrip('/')}/v2/orders/{order.broker_order_id}"
        resp = await self.client.delete(url, headers=self._headers())
        if resp.status_code in {200, 204}:
            order.status = "canceled"
            await db.commit()
            return {"ok": True, "status": order.status, "broker_mode": order.broker_mode}

        return {"ok": False, "status": order.status, "broker_mode": order.broker_mode, "message": resp.text}

    async def sync_positions(self, db: AsyncSession, user: User) -> dict:
        if not self._configured():
            return {"synced": 0, "broker_mode": self.mode, "message": "Alpaca credentials missing"}

        url = f"{settings.alpaca_base_url.rstrip('/')}/v2/positions"
        resp = await self.client.get(url, headers=self._headers())
        if resp.status_code >= 300:
            return {"synced": 0, "broker_mode": self.mode, "message": resp.text}

        items = resp.json()
        synced = 0
        for item in items:
            ticker = str(item.get("symbol", "")).upper()
            qty = float(item.get("qty") or 0.0)
            avg_cost = float(item.get("avg_entry_price") or 0.0)
            if not ticker:
                continue

            stmt = select(PortfolioPosition).where(PortfolioPosition.user_id == user.id, PortfolioPosition.ticker == ticker)
            pos = (await db.execute(stmt)).scalar_one_or_none()
            if pos is None:
                pos = PortfolioPosition(user_id=user.id, ticker=ticker, quantity=qty, avg_cost=avg_cost, updated_at=datetime.utcnow())
                db.add(pos)
            else:
                pos.quantity = qty
                pos.avg_cost = avg_cost
                pos.updated_at = datetime.utcnow()
            synced += 1

        await db.commit()
        return {"synced": synced, "broker_mode": self.mode}

    async def account_summary(self, db: AsyncSession, user: User) -> dict:
        if not self._configured():
            return {"broker_mode": self.mode, "message": "Alpaca credentials missing"}

        url = f"{settings.alpaca_base_url.rstrip('/')}/v2/account"
        resp = await self.client.get(url, headers=self._headers())
        if resp.status_code >= 300:
            return {"broker_mode": self.mode, "message": resp.text}

        data = resp.json()
        return {
            "broker_mode": self.mode,
            "account_status": data.get("status"),
            "equity": float(data.get("equity") or 0.0),
            "buying_power": float(data.get("buying_power") or 0.0),
            "cash": float(data.get("cash") or 0.0),
            "portfolio_value": float(data.get("portfolio_value") or 0.0),
        }


class StubExternalBrokerAdapter(BrokerAdapter):
    def __init__(self, mode: str) -> None:
        self.mode = mode

    async def execute_order(
        self,
        db: AsyncSession,
        user: User,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str,
        requested_price: float | None,
        market_price: float,
    ) -> ExecResult:
        return ExecResult(
            id=None,
            ticker=ticker,
            side=side,
            quantity=quantity,
            filled_price=0.0,
            status="pending_adapter",
            created_at=datetime.utcnow(),
            broker_mode=self.mode,
            message=f"{self.mode} adapter scaffold is ready; wire your API credentials/execution client.",
        )


class BrokerService:
    def __init__(self) -> None:
        self._paper = PaperBrokerAdapter()
        self._alpaca = AlpacaBrokerAdapter()
        self._ibkr = StubExternalBrokerAdapter("ibkr")

    async def close(self) -> None:
        await self._alpaca.close()

    @property
    def mode(self) -> str:
        mode = getattr(settings, "broker_mode", "paper").strip().lower() or "paper"
        return mode

    def adapter(self) -> BrokerAdapter:
        mode = self.mode
        if mode == "alpaca":
            return self._alpaca
        if mode == "ibkr":
            return self._ibkr
        return self._paper

    async def execute(
        self,
        db: AsyncSession,
        user: User,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str,
        requested_price: float | None,
        market_price: float,
    ) -> ExecResult:
        return await self.adapter().execute_order(db, user, ticker, side, quantity, order_type, requested_price, market_price)

    async def order_status(self, db: AsyncSession, user: User, order: PaperOrder) -> dict:
        return await self.adapter().get_order_status(db, user, order)

    async def cancel_order(self, db: AsyncSession, user: User, order: PaperOrder) -> dict:
        return await self.adapter().cancel_order(db, user, order)

    async def sync_positions(self, db: AsyncSession, user: User) -> dict:
        return await self.adapter().sync_positions(db, user)

    async def account_summary(self, db: AsyncSession, user: User) -> dict:
        return await self.adapter().account_summary(db, user)
