import asyncio
import datetime
import json
from fastapi import APIRouter, WebSocketDisconnect, WebSocket
from typing import Any, Dict, List, Tuple


router = APIRouter()




# --------------------------------------------------------------------
# WEBSOCKET: Connection Manager & Endpoints
# --------------------------------------------------------------------

# --------------------------------------------------------------------
# Production Usage Examples (as comments)
# --------------------------------------------------------------------
"""
Usage Examples:

1. Login API:
   POST /login
   - For traditional login, send form data:
       username: "john_doe"
       password: "secret123"
   - For facial login, send form data:
       username: "john_doe"
       facial_image: (UploadFile: image file)
   Response includes a JWT token, token_expiration, and dashboard_url.

2. Protected Endpoints:
   Include the JWT token in the Authorization header as:
       Authorization: Bearer <token>
   The dependency get_current_user will verify token validity, expiration, and inactivity.

3. Logout:
   POST /logout (with the token in Authorization header) to clear the token from the DB.

4. Logs API:
   GET /logs?organization_id=<org_uuid>&log_date=2025-02-07
   If log_date is omitted, logs for the current date are returned.

5. WebSocket for Notifications:
   Connect to: ws://<server>/ws/notifications/<organization_id>/<user_id>
   The server sends periodic reminders (e.g., every 60 seconds).

6. WebSocket for Chat:
   Connect to: ws://<server>/ws/chat/<organization_id>/<user_id>
   Send JSON messages like:
       {"recipient_id": "recipient_uuid", "message": "Hello!"}
   If the recipient is offline, messages will be stored and delivered upon reconnection.

7. Inactivity Handling:
   If no request is received from a user for 15 minutes, the token’s last_activity check in get_current_user
   will delete the token and force the user to log in again.

8. Token Event Trigger:
   On successful login, a token record is inserted into the Token model (see authenticate_user function).

This code is designed to be modular, secure, and production-ready. Adjust helper functions,
configuration, and logging as needed in your environment.
"""

# Finally, include router in your main FastAPI app.
# For example:
# from fastapi import FastAPI
# app = FastAPI()
# app.include_router(router, prefix="/api/auth")



class ConnectionManager:
    def __init__(self):
        # Active connections keyed by organization_id.
        # Keyed by organization_id → list of all WebSockets in that org
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Keyed by (organization_id, user_id) → list of WebSockets for that user
        self.user_connections: Dict[Tuple[str, str], List[WebSocket]] = {}
        # Lock to prevent race conditions during connect/disconnect
        self._lock = asyncio.Lock()

    
    async def register(self, organization_id: str, user_id: str, websocket: WebSocket):
        """
        Call this _after_ you have validated the token and decided to accept() the WebSocket.
        This will simply record in-memory that this particular websocket belongs to:
          - organization_id (for broadcasting to entire org)
          - (organization_id, user_id) (for sending personal messages).
        """
        async with self._lock:
            self.active_connections.setdefault(organization_id, []).append(websocket)
            self.user_connections.setdefault((organization_id, user_id), []).append(websocket)

    async def unregister(self, organization_id: str, user_id: str, websocket: WebSocket):
        """
        Remove this WebSocket from both the org’s list and the user’s list.
        """
        async with self._lock:
            # Remove from active_connections
            conns = self.active_connections.get(organization_id, [])
            if websocket in conns:
                conns.remove(websocket)
                if not conns:
                    del self.active_connections[organization_id]

            # Remove from user_connections
            key = (organization_id, user_id)
            user_conns = self.user_connections.get(key, [])
            if websocket in user_conns:
                user_conns.remove(websocket)
                if not user_conns:
                    del self.user_connections[key]
    
    async def unregister_user(self, organization_id: str, user_id: str):
        """
        Force-close ALL WebSockets for this (org, user).
        """
        key = (organization_id, user_id)
        # snapshot the list so we can mutate the original safely
        conns = list(self.user_connections.get(key, []))
        for ws in conns:
            # 1) remove it from our maps immediately
            await self.unregister(organization_id, user_id, ws)

            # 2) then ask it to close — but guard against double-close
            try:
                await ws.close(code=1001)  # normal closure
            except RuntimeError:
                # already closed, ignore
                pass

    async def connect(self, organization_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(organization_id, []).append(websocket)

    def disconnect(self, organization_id: str, websocket: WebSocket):
        if organization_id in self.active_connections and websocket in self.active_connections[organization_id]:
            self.active_connections[organization_id].remove(websocket)

    # async def send_personal_message(self, message: str, websocket: WebSocket):
    #     await websocket.send_text(message)

    async def send_personal_message(self, organization_id: str, user_id: str, message: str):
        """
        Send `message` to every WebSocket that belongs to (organization_id, user_id).
        If that user is offline (no entry in user_connections), this is a no-op.
        """
        key = (organization_id, user_id)
        print(f"key in send_personal_message:: {key}")
        if key not in self.user_connections:
            return
        print(f"user connections:: {self.user_connections}")
        for ws in list(self.user_connections[key]):
            try:
                await ws.send_text(message)
            except Exception:
                # If sending fails, we ignore; the next heartbeat/disconnect will clean it up.
                pass

    # async def broadcast(self, organization_id: str, message: str):
    #     if organization_id in self.active_connections:
    #         for connection in self.active_connections[organization_id]:
    #             await connection.send_text(message)

    async def broadcast(self, organization_id: str, message: str):
        """
        Send `message` to every WebSocket currently connected under organization_id.
        """
        if organization_id not in self.active_connections:
            return
        for ws in list(self.active_connections[organization_id]):
            try:
                await ws.send_text(message)
            except Exception:
                # If sending fails, ignore; cleanup happens in disconnect.
                pass
    
    async def broadcast_json(self, organization_id: str, obj: Any):
        if organization_id not in self.active_connections:
            return
        for ws in list(self.active_connections[organization_id]):
            try:
                await ws.send_json(obj)
            except:
                pass

manager = ConnectionManager()

@router.websocket("/ws/notifications/{organization_id}/{user_id}")
async def websocket_notifications(websocket: WebSocket, organization_id: str, user_id: str):
    """
    WebSocket for sending real-time notifications/reminders to a user.
    
    **Usage Example:**  
      Connect from the frontend to:  
      ws://<server>/ws/notifications/<organization_id>/<user_id>
      
    The server sends periodic reminders (e.g., about inactivity or token expiration).
    """
    await manager.connect(organization_id, websocket)
    try:
        while True:
            await asyncio.sleep(60)  # Send a reminder every 60 seconds.
            reminder = f"Reminder: User {user_id}, please stay active to avoid auto-logout."
            await manager.send_personal_message(reminder, websocket)
    except WebSocketDisconnect:
        manager.disconnect(organization_id, websocket)

# In-memory storage for pending chat messages.
pending_messages: Dict[str, List[Dict]] = {}

@router.websocket("/ws/chat/{organization_id}/{user_id}")
async def websocket_chat(websocket: WebSocket, organization_id: str, user_id: str):
    """
    WebSocket endpoint for real-time chat/messaging between users.
    
    **Usage Example:**  
      Connect from the frontend to:  
      ws://<server>/ws/chat/<organization_id>/<user_id>
      
    If the recipient is offline, messages are stored in memory (pending for up to 24 hours).
    After 24 hours, messages expire.
    """
    await manager.connect(organization_id, websocket)
    try:
        # Send any pending messages for the connected user.
        if user_id in pending_messages:
            for msg in pending_messages[user_id]:
                await websocket.send_text(msg["message"])
            # Retain only messages that are less than 24 hours old.
            pending_messages[user_id] = [msg for msg in pending_messages[user_id]
                                          if (datetime.datetime.utcnow() - msg["timestamp"]).total_seconds() < 86400]
        while True:
            data = await websocket.receive_text()
            # Expect data as JSON: {"recipient_id": "user_uuid", "message": "text"}
            data_obj = json.loads(data)
            recipient = data_obj.get("recipient_id")
            message = data_obj.get("message")
            sent = False
            # If the recipient is connected, deliver immediately.
            if recipient in manager.active_connections:
                for conn in manager.active_connections[recipient]:
                    await conn.send_text(message)
                sent = True
            # Otherwise, store the message in pending_messages.
            if not sent:
                pending_messages.setdefault(recipient, []).append({
                    "message": message,
                    "timestamp": datetime.datetime.utcnow()
                })
    except WebSocketDisconnect:
        manager.disconnect(organization_id, websocket)