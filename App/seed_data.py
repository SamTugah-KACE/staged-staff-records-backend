# app/seed_data.py
# app/seed_superadmin.py
import asyncio, uuid
from sqlalchemy import select
from database.db_session import AsyncSessionLocal
from Models.superadmin import SuperAdmin
from Utils.security import Security

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


RAW_PASS  = "SuperSecurePass!23"
RAW_KEY   = "UltraSecretKey#42"

def hash_password(password: str) -> str:
        return pwd_context.hash(password)

async def seed_superadmin():
    async with AsyncSessionLocal() as session:
        q = await session.execute(select(SuperAdmin).where(SuperAdmin.username=="superadmin"))
        sa = q.scalars().first()
        if not sa:
            sa = SuperAdmin(
                id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
                username="superadmin",
                email="samuel.kusi-duah@gi-kace.gov.gh",
                hashed_password=hash_password(RAW_PASS),
                security_key_hash=hash_password(RAW_KEY),
            )
            session.add(sa)
            await session.commit()

if __name__=="__main__":
    asyncio.run(seed_superadmin())
