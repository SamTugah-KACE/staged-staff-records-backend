# src/api/deps_ws.py
import asyncio
from uuid import UUID
import anyio
from fastapi import HTTPException, WebSocket, status, Depends, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security.http import HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session
from Models.Tenants.role import Role
from Crud.auth import _decode_and_validate_token, get_current_user    # your HTTP function
from database.db_session import get_db
from jose import jwt, JWTError
from Models import models
from Utils.config import ProductionConfig

settings = ProductionConfig()

bearer_scheme = HTTPBearer(auto_error=False)

# async def get_current_user_ws(
#     websocket: WebSocket,
#     db: Session = Depends(get_db),
# ):
#     """
#     1) Read the `Authorization: Bearer <token>` header from the WebSocket handshake.
#     2) Wrap it into HTTPAuthorizationCredentials.
#     3) Call your existing get_current_user to do all the work.
#     """
#     # manually run the HTTPBearer on the WebSocket scope
#     credentials: HTTPAuthorizationCredentials = await bearer_scheme.__call__(websocket)
#     if credentials is None or credentials.scheme.lower() != "bearer":
#         await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
#         return

#     try:
#         user_ctx = await get_current_user(credentials, db)
#         return user_ctx
#     except Exception:
#         # invalid token, expired, inactivity, etc.
#         await websocket.close(code=status.WS_1008_POLICY_VIOLATION)



async def get_current_user_ws(token: str, db: Session):
    """
    Decode JWT 'sub' → user.id, fetch User.
    Raises if invalid.
    """
    try:
        print(f"\n\nTOKEN: {token}   \n\n")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        print("payload:: ", payload)
        user_id: str = payload.get("user_id")
        print("user_id: ", user_id)
        if not user_id:
            raise JWTError()
    except JWTError:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)
    return user


# async def get_current_user_ws(token: str, db: Session) -> models.User:
#     # 1) decode + validate exactly like HTTP
#     try:
#         token_data = await anyio.to_thread.run_sync(
#             lambda: asyncio.run(_decode_and_validate_token(token, db))
#         )
#     except HTTPException:
#         raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)

#     # 2) lookup user by UUID
#     try:
#         user_id = UUID(token_data["user_id"])
#     except Exception:
#         raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)

#     user = db.query(models.User).get(user_id)
#     if not user:
#         raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)

#     # 3) verify role still exists
#     role_obj = db.query(Role).get(UUID(token_data["role_id"]))
#     if not role_obj:
#         raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)

#     return user