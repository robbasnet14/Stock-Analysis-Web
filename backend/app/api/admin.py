from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import require_roles
from app.models.user import User


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require_roles("admin"))):
    rows = list((await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all())
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "role": u.role,
                "telegram_chat_id": u.telegram_chat_id,
                "created_at": u.created_at,
            }
            for u in rows
        ]
    }


@router.post("/users/{user_id}/role")
async def set_user_role(
    user_id: int,
    role: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    role = role.strip().lower()
    if role not in {"admin", "trader", "viewer"}:
        raise HTTPException(status_code=400, detail="Invalid role")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role
    await db.commit()
    return {"ok": True, "user_id": user.id, "role": user.role}
