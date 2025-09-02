import asyncio
import datetime
import json
from typing import Dict, List
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from Apis.default import create_default
from Apis.routers import api
from Apis.deps_ws import get_current_user_ws
from Apis.summary import _build_summary_payload
from Apis.summary_listeners import register_summary_listeners
from migration_script import run_migrations
from Models.Tenants.organization import Organization
from Service.data_input_handlers import autodiscover_handlers
from Models.models import Dashboard, User, Employee, EmployeeDataInput
from Models.Tenants.role import Role
from database.db_session import get_db, temp_db, SessionLocal
from sqlalchemy.orm import Session, joinedload
from notification.socket import manager
from Utils.daily_checks import schedule_daily_checks
import logging
from Utils.config import config
from seed_data import seed_superadmin
from Utils.security import Security
from sqlalchemy import and_, select
from Utils.config import ProductionConfig


# src/api/ws_employee.py

# from Apis.deps_ws import get_current_user_ws
# from Service.employee_aggregator import get_employee_full_record
from Crud.auth import require_permissions, require_hr_dashboard, ensure_hr_dashboard_ws
from Models.models import Employee



settings = ProductionConfig()



# # Initialize the global Security instance.
# # In a multi-tenant system sharing one schema, a common secret key is often used.
global_security = Security(secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM, token_expire_minutes=480)



logger = logging.getLogger(__name__)
# logger = logging.getLogger("uvicorn.error")
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize FastAPI app
app = FastAPI(
    title="Staff Management and Appraisal System",
    description="A robust system for managing staff records, appraisals, and related functionalities.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# Static Files (if needed)
# app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/static", StaticFiles(directory=config.STORAGE_ROOT), name="static")


# CORS Configuration
origins = [
    f"http://localhost:3000",  # React development
    "https://staff-records-superadmin-ui.onrender.com",
    "{settings.SUPERADMIN_UI_URL}",
    "{settings.TENANT_URL}",
    "https://gi-kace-solutions.onrender.com",  # Update with production frontend URL
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api)

# Root Endpoint
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Staff Management and Appraisal System API!"}

@app.websocket("/ws/notifications/{organization_id}/{user_id}")
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


# @app.websocket("/ws/form-design/{organization_id}/{user_id}")
# async def websocket_form_design(
#     websocket: WebSocket, 
#     organization_id: str, 
#     user_id: str, 
#     db: Session = Depends(get_db)
# ):
#     """
#     WebSocket endpoint that sends the saved form design for the organization.
#     The design includes the field definitions and a precompiled submit function.
#     """
#     await websocket.accept()
#     try:
#         # Retrieve the dashboard entry (assumes one design per organization for this scenario)
#         dashboard = db.query(Dashboard).filter(
#             Dashboard.organization_id == organization_id,
#             Dashboard.user_id == user_id
#         ).first()
#         if dashboard and dashboard.dashboard_data:
#             payload = {"formDesign": dashboard.dashboard_data}
#         else:
#             payload = {"formDesign": None}
#         await websocket.send_text(json.dumps(payload))
#         # Optionally keep connection alive for live updates.
#         while True:
#             await asyncio.sleep(60)
#     except WebSocketDisconnect:
#         logger.info(f"WebSocket disconnected for org {organization_id}, user {user_id}")
#     except Exception as exc:
#         logger.error(f"Error in websocket_form_design: {exc}")
#         raise HTTPException(status_code=500, detail="Internal server error")



@app.get("/api/organizations/{organization_id}/form-design")
def get_form_design(organization_id: str, db: Session = Depends(get_db)):
    form = (
        db.query(Dashboard)
        .filter(Dashboard.organization_id == organization_id, Dashboard.dashboard_name == "User Registration Form")
        .first()
    )
    if not form:
        raise HTTPException(status_code=404, detail="Form design not found.")
    return form.dashboard_data


@app.websocket("/ws/form-design/{organization_id}/{user_id}")
async def websocket_form_design(
    websocket: WebSocket,
    organization_id: str,
    user_id: str,
    db=Depends(get_db),
):
    # 1) Accept & register
    await websocket.accept()
    await manager.register(organization_id, user_id, websocket)
    try:
        # 2) Fetch form design once
        dash = (
            db.query(Dashboard)
              .filter_by(organization_id=organization_id, user_id=user_id)
              .first()
        )
        payload = {"formDesign": dash.dashboard_data if dash else None}
        await websocket.send_json(payload)

        # 3) Enter receive loop to keep connection alive
        while True:
            # wait for any client message—or a ping/pong—so the socket isn't idle
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                # client closed
                break
            except Exception:
                # ignore stray errors (e.g. binary frames)
                continue

    except Exception as exc:
        logger.error(f"ws/form-design error: {exc}")
        # You could send an error frame here, but we'll just close.
    finally:
        # 4) Clean up registration
        await manager.unregister(organization_id, user_id, websocket)
        logger.info(f"WebSocket closed for org={organization_id}, user={user_id}")
        

@app.websocket("/ws/chat/{organization_id}/{user_id}")
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



def extract_attachments(data: dict) -> list[dict]:
    """
    Only consider items whose key contains 'path' as attachments.
    Values may be:
      - dict of {filename: url}
      - JSON‐encoded dict strings
    """
    attachments = []
    for key, val in data.items():
        if "path" not in key.lower():
            continue

        # Case 1: native dict
        if isinstance(val, dict):
            for fn, url in val.items():
                attachments.append({"filename": fn, "url": url})
            continue

        # Case 2: JSON‐encoded dict string
        if isinstance(val, str) and val.strip().startswith("{") and val.strip().endswith("}"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    for fn, url in parsed.items():
                        attachments.append({"filename": fn, "url": url})
                    continue
            except json.JSONDecodeError:
                pass

    return attachments


@app.websocket("/ws/employee-inputs")
async def ws_employee_inputs(
    websocket: WebSocket,
    token: str = Query(...),
    organization_id: str = Query(...),
    db: Session = Depends(get_db),
):
    # 1) Try to authenticate; if expired/invalid, this will raise WebSocketDisconnect
    try:
        user = await global_security.get_current_user_ws(token, db)
        ensure_hr_dashboard_ws(user)
    except WebSocketDisconnect:
        # Close with 1008 so client knows it’s an auth issue
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2) Tenant check
    if str(user.organization_id) != organization_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
   

    # 2) Accept connection
    # await manager.connect(organization_id, websocket)
    await websocket.accept()
    await manager.register(organization_id, str(user.id), websocket)

    try:
        # 6) Keep-alive ping loop
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        # manager.disconnect(organization_id, websocket)
        await manager.unregister(organization_id, str(user.id), websocket)

    except Exception:
        import logging; logging.exception("Unexpected WS error")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        await manager.unregister(organization_id, str(user.id), websocket)








# Exception Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
             "message": exc.detail,
                 "error": exc.detail,
        },
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled server error")
    return JSONResponse(
        status_code=500,
        content={ 
                 "message": exc.detail,
                 "error": exc.detail,
                 },
    )

# Startup Event
# @app.on_event("startup")
async def on_startup():
    """
    Actions to perform on application startup.
    Example: Initializing a temporary database, loading configurations, etc.
    """,
    try:
        # Run pending migrations
        # await asyncio.to_thread(run_migrations)
        # Initialize database schema
        temp_db()

        # Create a synchronous session
        db: Session = SessionLocal()
        try:
            create_default(db=db)

        finally:
            db.close()
        
        # Seed the superadmin if not already present
        await seed_superadmin()

        autodiscover_handlers()
        
        # Start the APScheduler job for daily checks.
        schedule_daily_checks()

        register_summary_listeners()
        
        # Register employee listeners for automatic updates
        from Apis.employee_listeners import register_employee_listeners
        register_employee_listeners()
        
        print("Application startup tasks completed successfully.")

        print("Application startup tasks completed.")

    except Exception as e:
        print(f"An error occurred during startup: {str(e)}")
        raise RuntimeError("Failed to start the application. Please check the logs.") from e
    

app.add_event_handler("startup", on_startup)
    


# Shutdown Event
# @app.on_event("shutdown")
async def on_shutdown():
    """
    Actions to perform on application shutdown.
    Example: Closing database connections, releasing resources, etc.
    """
    # app.state.db.close()
    print("Application shutdown tasks completed.")
    

app.add_event_handler("shutdown", on_shutdown)
