import json
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID
from Schemas.schemas import EmailConfigCreate
from Models.models import SystemSetting  # or Organization.settings JSON for App1

class EmailConfigService:
    def __init__(self, db: Session, schema_based: bool = False):
        self.db = db
        self.schema_based = schema_based

    def create(self, org_id: UUID, cfg: EmailConfigCreate):
        payload = cfg.dict()
        new_id = str(uuid.uuid4())
        if self.schema_based:
            sql = text("""
                UPDATE public.organization
                SET settings = jsonb_set(
                    coalesce(settings, '{}'::jsonb),
                    'email',
                    cast(:cfg AS jsonb),
                    true
                )
                WHERE id = :org_id
            """)
            params = {"cfg": json.dumps(payload), "org_id": str(org_id)}
        else:
        
            sql = text("""
            WITH upsert AS (
            UPDATE public.system_settings
                SET setting_value = cast(:cfg AS jsonb)
            WHERE organization_id = :org_id
                AND setting_name = 'email'
            RETURNING *
            )
            INSERT INTO public.system_settings (id, organization_id, setting_name, setting_value)
            SELECT :new_id, :org_id, 'email', cast(:cfg AS jsonb)
            WHERE NOT EXISTS (SELECT 1 FROM upsert)
            """)
            params = {
            "new_id": new_id,
            "org_id": str(org_id),
            "cfg": json.dumps(payload)
            }
    
        self.db.execute(sql, params)
        self.db.commit()
        return payload

    def read(self, org_id: UUID):
        if self.schema_based:
            row = self.db.execute(
                text("SELECT settings->'email' FROM public.organization WHERE id = :org_id"),
                {"org_id": str(org_id)}
            ).scalar_one_or_none()
        else:
            row = self.db.execute(
                text("SELECT setting_value FROM public.system_settings WHERE organization_id = :org_id AND setting_name='email'"),
                {"org_id": str(org_id)}
            ).scalar_one_or_none()
        return row

    def update(self, org_id: UUID, cfg: dict):
        # update is identical to create (upsert semantics)
        return self.create(org_id, EmailConfigCreate.parse_obj(cfg))

    def delete(self, org_id: UUID):
        if self.schema_based:
            sql = text("""
                UPDATE public.organization
                   SET settings = (settings - 'email')
                 WHERE id = :org_id
            """)
            self.db.execute(sql, {"org_id": str(org_id)})
        else:
            result = self.db.execute(
            text("""
                DELETE FROM public.system_settings
                 WHERE organization_id = :org_id AND setting_name = 'email'
                 RETURNING 1
            """),
            {"org_id": str(org_id)}
            ).rowcount

            if result == 0:
                return False
            
        self.db.commit()
        return True
