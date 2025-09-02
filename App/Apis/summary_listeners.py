# src/api/summary_listeners.py

import asyncio
from sqlalchemy import event
from sqlalchemy.orm import Session
from Models.Tenants.organization import Branch, PromotionPolicy, Tenancy, Bill, Payment
from Models.models import Department, User, Employee
from Models.Tenants.role import Role
from .summary_broadcaster import broadcast_summary

# List all models whose INSERT/UPDATE/DELETE should trigger a summary refresh:
TARGET_MODELS = [Branch, Department, Role, PromotionPolicy, Tenancy, Bill, Payment, User, Employee]

def _after_change(mapper, connection, target):
    # This handler runs inside SQLAlchemy’s sync world; but
    # SQLAlchemy 1.4+ gives us .info["session"] to retrieve the Session
    db: Session = connection.info.get("session")
    if db is None:
        # Fallback: new Session(bind=connection) — but better to attach Session into connection.info.
        print("❌ No session found in connection.info, cannot broadcast summary")
        return
    org_id = str(target.organization_id)
    # Broadcast without blocking the current transaction
    asyncio.get_event_loop().create_task(broadcast_summary(org_id, db))

def register_summary_listeners():
    for model in TARGET_MODELS:
        # after_insert, after_update, and after_delete all fire
        event.listen(model, 'after_insert', _after_change)
        event.listen(model, 'after_update', _after_change)
        event.listen(model, 'after_delete', _after_change)
