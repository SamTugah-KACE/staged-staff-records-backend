# dependencies.py
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from Utils.config import ProductionConfig
from database.db_session import get_async_db
from Models.superadmin import SuperAdmin
from Utils.sup_security import decode_jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/super-auth/superadmin/auth/token")

settings = ProductionConfig()

async def get_current_superadmin(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> SuperAdmin:
    try:
        payload = decode_jwt(token)
        admin_id = payload.get("sub")
        if not admin_id:
            raise
        admin_uuid = uuid.UUID(admin_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    result = await db.execute(
        select(SuperAdmin).where(SuperAdmin.id == admin_uuid, SuperAdmin.is_active.is_(True))
    )
    admin = result.scalars().first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return admin


async def get_refresh_token(request: Request) -> str:
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return token