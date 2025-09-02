# src/api/ws_notifications.py
import asyncio
from fastapi import APIRouter, WebSocket, Depends, WebSocketDisconnect, status
from .deps_ws import get_current_user_ws
from notification.socket import manager

router = APIRouter()

@router.websocket("/ws/notifications/{organization_id}/{user_id}")
async def websocket_notifications(
    websocket: WebSocket,
    organization_id: str,
    user_id: str,
    user_ctx: dict = Depends(get_current_user_ws),
):
    # ensure they are the same user or an admin
    if str(user_ctx["id"]) != user_id and user_ctx["role"] != "admin":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(organization_id, websocket)
    try:
        while True:
            await asyncio.sleep(60)
            reminder = f"Reminder for {user_ctx['user'].username}"
            await manager.send_personal_message(reminder, websocket)
    except WebSocketDisconnect:
        manager.disconnect(organization_id, websocket)
