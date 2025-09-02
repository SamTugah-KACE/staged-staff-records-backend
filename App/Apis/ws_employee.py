# src/api/ws_employee.py
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, Depends, WebSocketDisconnect, status
from .deps_ws import get_current_user_ws
from Service.employee_aggregator import get_employee_full_record
from Crud.auth import require_permissions
from sqlalchemy.orm import Session
from database.db_session import get_db
from Models.models import Employee
from fastapi.encoders import jsonable_encoder
from notification.socket import manager

router = APIRouter()

# require_permissions decorator checks if the user has the required permissions
# @require_permissions("hr:dashboard")

# This WebSocket endpoint allows real-time updates for an employee's data
# It accepts a WebSocket connection and listens for messages.

@router.websocket("/ws/employee/{organization_id}/{employee_id}")
async def employee_ws(
    websocket: WebSocket,
    organization_id: str,
    employee_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    WebSocket Endpoint:
      wss://<server>/ws/employee/{organization_id}/{employee_id}?token=<jwt>

    Only the employee itself or an HR user in that organization may connect.
    Once accepted, we immediately send one initial payload (their full record),
    then listen for "refresh" requests and re‐send updated data.
    """
    # 1) Authenticate & authorize before accepting:
    try:
        user = await get_current_user_ws(token, db)
    except Exception:
        # Token invalid/expired → reject handshake
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2) Tenant isolation:
    if str(user.organization_id) != organization_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3) Check that the user is either:
    #    - the employee whose record is being viewed, OR
    #    - has "hr:dashboard" permission
    emp_obj: Optional[Employee] = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp_obj:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # If the email doesn’t match, require HR permission
    if emp_obj.email != user.email:
        try:
            require_permissions(user, ["staff:dashboard"])
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # 4) All checks pass → accept the WebSocket and register it
    await websocket.accept()
    await manager.register(organization_id, str(user.id), websocket)

    try:
        # 5) Send the “initial” snapshot
        initial_payload = get_employee_full_record(db, employee_id)
        wrapped = {"type": "initial", "payload": initial_payload}
        await websocket.send_text(json.dumps(wrapped, default=lambda o: str(o)))

        # 6) Enter heartbeat loop with token revalidation
        try:
            while True:
                # Wait up to 60 seconds for client ping or automatic wake-up
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                    # Client sent a message - handle refresh requests
                    if msg == "refresh":
                        updated_payload = get_employee_full_record(db, employee_id)
                        update_msg = {"type": "update", "payload": updated_payload}
                        await websocket.send_text(json.dumps(update_msg, default=lambda o: str(o)))
                except asyncio.TimeoutError:
                    # No ping from client, but that's okay - we'll validate token
                    pass

                # Re-validate token every 60 seconds
                try:
                    # Re-authenticate the user to check if token is still valid
                    reauth_user = await get_current_user_ws(token, db)
                    if str(reauth_user.id) != str(user.id) or str(reauth_user.organization_id) != organization_id:
                        # Token is valid but for different user/org - close connection
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        break
                except Exception:
                    # Token is invalid/expired - close connection
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    break

        except WebSocketDisconnect:
            pass  # Client disconnected normally

    except WebSocketDisconnect:
        # 7) Clean up
        await manager.unregister(organization_id, str(user.id), websocket)
    except Exception:
        # Unexpected error → close & cleanup
        if websocket.client_state.name != "CLOSED":
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        await manager.unregister(organization_id, str(user.id), websocket)

# @router.websocket("/ws/employee/{employee_id}")
# async def employee_ws(
#     websocket: WebSocket,
#     employee_id: str,
#     # user_ctx: dict = Depends(get_current_user_ws),
#     db: Session = Depends(get_db),
# ):
   

#     await websocket.accept()
#     try:
        # send initial payload
        # await websocket.send_json({
        #     "type": "initial",
        #     "payload": get_employee_full_record(db, employee_id)
        # })

         # send initial payload (convert UUID→str, datetime→ISO, etc.)
    #     initial = {"type": "initial", "payload": get_employee_full_record(db, employee_id)}
    #     await websocket.send_json(jsonable_encoder(initial))

    #     while True:
    #         msg = await websocket.receive_text()
    #         if msg == "refresh":
    #             # await websocket.send_json({
    #             #   "type": "update",
    #             #   "payload": get_employee_full_record(db, employee_id)
    #             # })
    #             update = {"type": "update", "payload": get_employee_full_record(db, employee_id)}
    #             await websocket.send_json(jsonable_encoder(update))

    # except WebSocketDisconnect:
    #     return



