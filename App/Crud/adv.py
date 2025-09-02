from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict






# Role Cache for Optimization
class RoleCache:
    def __init__(self):
        self.cache = {}

    async def get_or_create_role(self, db: AsyncSession, role_model, role_name: str, permissions: Dict, organization_id: UUID):
        key = (role_name, organization_id)
        if key not in self.cache:
            role = await db.query(role_model).filter(
                role_model.name == role_name,
                role_model.organization_id == organization_id
            ).first()

            if not role:
                role = role_model(name=role_name, permissions=permissions, organization_id=organization_id)
                db.add(role)
                await db.commit()
                await db.refresh(role)

            self.cache[key] = role

        return self.cache[key]