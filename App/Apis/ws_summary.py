import asyncio
from fastapi import Depends, Query, WebSocket, WebSocketDisconnect, APIRouter, status
from fastapi.websockets import WebSocketState
from sqlalchemy.orm import Session
from Models.Tenants.organization import Organization
from database.db_session import get_db
from .deps_ws import get_current_user_ws
from notification.socket import manager
import json
from uuid import UUID
from .summary import _build_summary_payload
from Models.Tenants.role import Role
from fastapi.encoders import jsonable_encoder
from Utils.security import Security
from Utils.config import ProductionConfig

router = APIRouter()

settings = ProductionConfig()

 # In a multi-tenant system sharing one schema, a common secret key is often used.
global_security = Security(secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM, token_expire_minutes=480)

@router.websocket("/ws/summary/{organization_id}/{user_id}")
async def websocket_summary(
    websocket: WebSocket,
    organization_id: str,
    user_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    # 1) Authenticate
    try:
        user = await global_security.get_current_user_ws(token, db)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2) Tenant + identity check
    if str(user.organization_id) != organization_id or str(user.id) != user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3) Accept & register
    await websocket.accept()
    await manager.register(organization_id, user_id, websocket)

    try:
        # 4) Validate org exists (use filter().first())
        try:
            org_uuid = UUID(organization_id)
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            await manager.unregister(organization_id, user_id, websocket)
            return

        org = db.query(Organization).filter(Organization.id == org_uuid).first()
        if not org:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            await manager.unregister(organization_id, user_id, websocket)
            return

        # 5) Build & send initial summary
        payload = await _build_summary_payload(db, org_uuid)
        message = {"type": "initial", "payload": payload}
        await websocket.send_json(message)

        # now enter a “heartbeat+ping” loop
        try:
            while True:
                # await asyncio.sleep(3600)
                # await websocket.receive_text()
                # 1️⃣ wait up to, say, 60 seconds for a client ping (optional)
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                    # if you want, you can respond to pings here
                except asyncio.TimeoutError:
                    # no ping — but that’s okay, we just wanted to wake up periodically
                    pass

                # 2️⃣ re-validate token
                if not await global_security.is_ws_token_valid(token, db):
                    # let the client know why we’re closing
                    if websocket.client_state != WebSocketState.CLOSED:
                        # await websocket.send_json({"type":"error", "reason":"token_expired"})
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    break

                # 3️⃣ (optional) send an update every X seconds
                # Note: Automatic updates are handled by database event listeners
                # in summary_listeners.py, so we don't need to poll here

            # end of loop
        except WebSocketDisconnect:
            pass
        finally:
            await manager.unregister(organization_id, user_id, websocket)

        # 6) Wait for “refresh”
        # while True:
        #     data = await websocket.receive_text()
        #     if data == "refresh":
        #         schema_obj = await _build_summary_payload(db, org_uuid)
        #         payload = jsonable_encoder(schema_obj)
        #         await websocket.send_json({"type": "update", "payload": payload})
        #         print("✅ sent update payload")
        #     else:
        #         continue

    except WebSocketDisconnect:
        await manager.unregister(organization_id, user_id, websocket)

    except Exception as exc:
        if websocket.client_state.name != "CLOSED":
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        await manager.unregister(organization_id, user_id, websocket)


# @router.websocket("/ws/summary/{organization_id}/{user_id}")
# async def websocket_summary(
#     websocket: WebSocket,
#     organization_id: str,
#     user_id: str,
#     token: str = Query(...),
#     db: Session = Depends(get_db),
# ):
#     """
#     WebSocket that immediately pushes the organization-wide summary counts, 
#     and will respond to "refresh" messages by re‐sending an updated snapshot.
#     Clients connect to:
#       wss://…/ws/summary/{org_id}/{user_id}?token=<jwt>
#     """
#     # 1) Authenticate
#     try:
#         print("WebSocket summary connection attempt with token:", token)
#         if not token:
#             await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
#             return
#         user = await get_current_user_ws(token, db)
#         print("user identified in ws summary:", user)
#     except Exception:
#         await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
#         return

#     print(f"WebSocket connection attempt for org_id={organization_id}, user_id={user_id}\n\n{str(user.organization_id) != organization_id or str(user.id) != user_id}")
#     # 2) Tenant + identity check
#     if str(user.organization_id) != organization_id or str(user.id) != user_id:
#         await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
#         return

#     # 3) Accept & register
#     await websocket.accept()
#     await manager.register(organization_id, user_id, websocket)

#     try:
#         # 4) Validate org_id as a UUID, ensure it exists
#         try:
#             org_uuid = UUID(organization_id)
#         except ValueError:
#             await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
#             await manager.unregister(organization_id, user_id, websocket)
#             return

#         org = db.query(Organization).get(org_uuid)
#         if not org:
#             await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
#             await manager.unregister(organization_id, user_id, websocket)
#             return

#         # 5) Build and send initial summary
#         initial_payload = await _build_summary_payload(db, org_uuid)
#         print("Initial payload for WebSocket summary:", initial_payload)
#         await websocket.send_text(json.dumps({"type": "initial", "payload": initial_payload}))

#         # 6) Wait for client “refresh” messages to re‐send updated payload
#         while True:
#             data = await websocket.receive_text()
#             if data == "refresh":
#                 new_payload = await _build_summary_payload(db, org_uuid)
#                 await websocket.send_text(json.dumps({"type": "update", "payload": new_payload}))
#             else:
#                 continue

#     except WebSocketDisconnect:
#         await manager.unregister(organization_id, user_id, websocket)
#     except Exception:
#         if websocket.client_state.name != "CLOSED":
#             await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
#         await manager.unregister(organization_id, user_id, websocket)