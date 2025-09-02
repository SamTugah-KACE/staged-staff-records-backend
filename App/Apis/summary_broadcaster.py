# src/api/summary_broadcaster.py
import asyncio, json
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from uuid import UUID

from .ws_summary import _build_summary_payload
from notification.socket import manager

async def broadcast_summary(org_id: str, db: Session):
    """
    Rebuild the summary for org_id and broadcast an 'update' to all sockets.
    """
    org_uuid = UUID(org_id)
    schema = await _build_summary_payload(db, org_uuid)
    payload = jsonable_encoder(schema)
    message = json.dumps({"type": "update", "payload": payload})
    # fire-and-forget
    asyncio.create_task(manager.broadcast(org_id, message))
