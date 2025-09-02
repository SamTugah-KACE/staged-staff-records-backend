import datetime
from uuid import uuid4, UUID
from cachetools import TTLCache
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, UploadFile, Query, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
from sqlalchemy.orm import Session, joinedload
from typing import Any, Dict, Optional, List, Union
from Utils.rate_limiter import RateLimiter
from database.db_session import get_db
from Models.models import User, Token, Dashboard, Employee
from Models.Tenants.organization import Organization
from Models.Tenants.role import Role
from Utils.security import Security  # contains verify_password and generate_token
from Service.email_service import EmailService, send_email_notification
from Utils.config import DevelopmentConfig
from email_validator import EmailNotValidError
from typing import List
import logging


# Initialize logger
logger = logging.getLogger(__name__)

from Schemas.schemas import UserSchema, EmployeeSchema

settings = DevelopmentConfig()

rate_limiter = RateLimiter(max_attempts=3, period=60)  # 5 attempts per 60 seconds

# Lightweight TTL in-memory cache
active_token_cache = TTLCache(maxsize=10000, ttl=3600)

# Initialize the global Security instance.
# In a multi-tenant system sharing one schema, a common secret key is often used.
global_security = Security(secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM, token_expire_minutes=60)

# def send_email_notification(recipient: str, subject: str, message: str) -> None:
#     """
#     Synchronously sends an email notification using the EmailService.
#     This function wraps the email sending methods provided by your email service.
#     """
#     try:
#         service = EmailService()
#         # Here we call the synchronous version (which internally runs the async call)
#         service.send_plain_text_email_sync([recipient], subject, message)
        
#     except EmailNotValidError as e:
#         # Log the error or handle invalid email addresses
#         raise Exception(f"Invalid email address: {recipient}") from e
#     except Exception as e:
#         # Log the exception as needed
#         raise Exception("Failed to send email notification.") from e


def is_facial_api_available() -> bool:
    """
    Checks the health of the external facial authentication API.
    It performs a GET request to the API's /health endpoint.
    Returns True if the API is up (HTTP 200); otherwise False.
    """
    url = f"{settings.FACIAL_AUTH_API_URL}/health"
    try:
        response = httpx.get(url, timeout=5.0)
        return response.status_code == 200
    except Exception as e:
        # Log the exception if desired
        return False

async def authenticate_facial(username: str, image: UploadFile) -> bool:
    """
    Sends a multipart/form-data POST request to the external facial
    authentication API with the provided username and image file.
    
    The external API should return JSON with an "authenticated" field.
    If the response is not HTTP 200 or the field is False, an exception is raised.
    """
    url = f"{settings.FACIAL_AUTH_API_URL}/authenticate"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Prepare the form data with the username and image file.
            # The external API is expected to handle a field named "username"
            # and "file" (with filename and content_type).
            form = {
                "username": username,
                "file": (image.filename, await image.read(), image.content_type)
            }
            response = await client.post(url, files=form)
            if response.status_code == 200:
                result = response.json()
                # Expect the external API to return {"authenticated": true/false}
                # return result.get("authenticated", False)
                # Check the message field to decide success.
                return result.get("message", "").lower() == "authentication successful"
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Facial authentication failed due to external API error."
                )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=504,
            detail="Facial authentication API request timed out."
        )

# ------------------------------------------------------------------------------
# 2) Helper: expire_old_tokens
# ------------------------------------------------------------------------------
def expire_old_tokens(db: Session, user_id: UUID, org_id: UUID) -> None:
    """
    Remove all tokens for this user/org whose expiration_period has passed.
    Call this BEFORE you check for concurrent logins.
    """
    now = datetime.utcnow()
    db.query(Token).filter(
        Token.user_id == user_id,
        Token.organization_id == org_id,
        Token.expiration_period <= now,
    ).delete(synchronize_session="fetch")
    db.commit()


# ==============================
# 1. AUTHENTICATE_USER FUNCTION
# ==============================
async def authenticate_user(
    background_task: BackgroundTasks,
    db: Session,
    username: str,
    password: Optional[str] = None,
    facial_image: Optional[UploadFile] = None,
    request: Request = None,
    response: Response = None
) -> Dict:
    """
    Two-way login for a multi-tenant system.

    Implements IP/User-Agent validation, prevents concurrent logins,
    utilizes token caching with TTL, and optimizes database queries.
    
    - If facial_image is provided and the external facial API is available,
      authenticate using facial recognition.
    - Otherwise, use traditional username/password.
    - Prevent concurrent logins: if an active token exists for the user, send an email notification and deny new login.
    - On successful login, generate a token, store it in the Token model, update last_login, and return user data
      along with the organization's dashboard access URL.
    """

    # Retrieve client IP and User-Agent
    client_ip = request.client.host
    user_agent = request.headers.get('user-agent', 'unknown')
    logger.info(f"Login attempt from IP: {client_ip}, User-Agent: {user_agent}")

    
    # 1. Retrieve user by username (assume usernames are unique)
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning(f"Invalid login attempt for username: {username} from IP: {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # 2. Enforce multi-tenancy: (you might later also verify organization is active)
    Organization.check_organization_active(user.organization_id, db)

    if user.is_active == False:
        raise HTTPException(status_code=400, detail="User not allowed to log-in due to the account been inactive.")
    
    # 3. Determine login option:
    login_option = None
    if facial_image is not None:
        if is_facial_api_available():
            # Resize the image to 300x300 (assume a helper function resize_image exists)
            resized_image = await resize_image(facial_image, width=300, height=300)
            if await authenticate_facial(username, resized_image):
                login_option = "facial"
            else:
                # If facial authentication fails, fallback to password authentication if provided
                if password is None:
                    logger.warning(f"Failed facial recognition and no password provided for username: {username} from IP: {client_ip}")
                    raise HTTPException(status_code=401, detail="Facial authentication failed and no password provided.")
                # Else, continue to password check below.
        else:
            # External facial API is down; fall back to password
            login_option = "password"
    
    # 4. If not using facial (or fallback), verify password.
    if login_option != "facial":
        if password is None:
            logger.warning(f"No password provided for username: {username} from IP: {client_ip}")
            raise HTTPException(status_code=401, detail="Password is required.")
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    
        # Apply rate limit before authentication
        rate_limiter.check_rate_limit(db, user, request)

        authenticate_password =  global_security.verify_password(password, user.hashed_password)
        print("\nauthenticate password: ", authenticate_password)
        if not authenticate_password:
            # (Optionally log failed attempt in rate limiter)
            rate_limiter.log_failed_attempt(user, request)  # Log failed attempt
            logger.warning(f"Invalid password for username: {username} from IP: {client_ip}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        login_option = "password"
    
    
    
    
    # 5. Prevent concurrent logins.
    existing_token = db.query(Token).filter(
        Token.user_id == user.id,
        Token.organization_id == user.organization_id,
        Token.expiration_period > datetime.datetime.utcnow()
    ).first()

    if existing_token:
        name = None
        # empID = None
        employee = db.query(Employee).filter(Employee.email == user.email, Employee.organization_id == user.organization_id).first()
        if not employee:
            name = None
        else:
            name = f"{employee.title} {employee.first_name}" if employee else user.username
            empID = employee.id
 

        if not name:
            name = user.username

        # Send email notification about attempted concurrent login.
        subject = "<strong>Concurrent Login Attempt Detected</strong>"
        message = f"<p>Dear {name}, a login attempt was made while your account is active on another device. </p>" \
                  f"<p>If this wasn't you, please contact support immediately.</p>"
        
        service = EmailService()
        await service.send_email(background_task, recipients=[user.email], subject=subject, html_body=message)
        background_task.add_task(
            EmailService.send_html, [user.email], subject, message
        )
        logger.warning(f"Concurrent login attempt detected for username: {username} from IP: {client_ip}")
        raise HTTPException(status_code=403, detail="User already logged in on another device. Please logout first.")
    

    # Reset failed login attempts on success
    rate_limiter.reset_attempts(user)

    # Prepare token payload (including last_activity for inactivity tracking).
    now_ts = datetime.datetime.utcnow().timestamp()

    # 6. Generate token data.
    token_payload = {
        "user_id": str(user.id),
        "username": user.username,
        "role_id": str(user.role_id),
        "organization_id": str(user.organization_id),
        "login_option": login_option,
        "iat": now_ts,
        "last_activity": now_ts
    }
    token_str =  global_security.generate_token(data=token_payload, expires_in=28800)
    # Set token expiration to 1 hour from now.
    token_expiration_dt = datetime.datetime.utcnow() + datetime.timedelta(seconds=28800)
    token_expiration = token_expiration_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")  # Token valid for 1 hour
    # token_expiration = (datetime.datetime.utcnow() + datetime.timedelta(seconds=3600)).strftime("%a, %d %b %Y %H:%M:%S GMT")  # Token valid for 1 hour

    print("\nGenerated token: ", token_str)

    print("\n\n\nDecode: ", await global_security.decode_token(token_str))
    
    # Cache the token with TTL
    # cache.set(token_str, token_payload, timeout=3600)  # Cache for 1 hour


    # 7. Save token to DB (simulate event trigger)
    new_token = Token(
        user_id=user.id,
        organization_id=user.organization_id,
        token=token_str,
        expiration_period=token_expiration_dt,
        login_option=login_option,
        last_activity=datetime.datetime.utcnow()
    )
    db.add(new_token)
    db.commit()
    
    # 8. Update user's last login timestamp
    user.last_login = datetime.datetime.utcnow()
    db.commit()

    org = db.query(Organization).filter(Organization.id == user.organization_id).first()

    dash = org.access_url
    
    # 9. Retrieve dashboard info (simulate choosing a dashboard based on organization's dashboards)
    dashboard = db.query(Dashboard).filter(
        Dashboard.organization_id == user.organization_id
    ).first()
    dashboard_url = dashboard.access_url if dashboard else f"{dash}"
    
    #10 set cookies
    response.set_cookie(
        key="token",
        value=token_str,
        httponly=True,
        secure=True,  # ensure HTTPS in production
        samesite='None',
        expires=token_expiration,
        path="/"
    )



    # Instead of returning the raw 'user' object, convert it using your schema:
    user_serialized = UserSchema.model_validate(user)
    employee = db.query(Employee).filter(
        Employee.email == user.email,
        Employee.organization_id == user.organization_id
    ).first()
    staff_serialized = EmployeeSchema.model_validate(employee) if employee else None

    logger.info(f"User {username} authenticated successfully from IP: {client_ip} using {login_option} method.")

    # 11. Return response.
    return {
        "name": f"{employee.title} {employee.first_name}" if employee else "",
        "staff_id": employee.id if employee else "",
        "image_path": user.image_path,
        "username": user.username,
        "user":user_serialized,
        "staff":staff_serialized,
        "email": user.email,
        "token": token_str,
        "token_expiration": token_expiration,
        "role": user.role.name,
        "permissions": user.role.permissions,
        "organization_id": user.organization_id,
        "organization_name": user.organization.name,
        "dashboard_url": dashboard_url,
        "login_option": login_option
    }

# ------------------------------
# Helper: Resize Image (stub)
# ------------------------------
async def resize_image(image_file: UploadFile, width: int, height: int) -> UploadFile:
    """
    Resizes the given image to the specified width and height.
    (Implement using PIL or another image library.)
    For now, we simply return the image_file.
    """
    # In production, load the image with PIL, resize, then re-save to a BytesIO and create a new UploadFile.
    return image_file



security = HTTPBearer()

# ============================================
# 2. GET CURRENT USER DEPENDENCY (TOKEN CHECK)
# ============================================


# --------------------------------------------------------------------
# GET CURRENT USER DEPENDENCY (Token Expiration & Inactivity Check)
# --------------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
) -> dict:
    """
    Retrieves the current user based on the provided JWT token.
    - Checks that the token is valid and not expired.
    - Checks inactivity (15 minutes threshold) and logs out if exceeded.
    - Updates the token's last_activity timestamp on each request.
    - Retrieves the user and associated role data.
    
    Returns a dictionary with keys:
      "user": the User model instance,
      "role": the user's role name,
      "permissions": the permissions from the user's role.
    """
    token_str = credentials.credentials
    print("get_current_user: ", token_str)
    token_data = await global_security.decode_token(token_str)
    print("token_data: ", token_data)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Check token expiration.
    current_ts = datetime.datetime.utcnow().timestamp()
    exp = token_data.get("exp")
    print("exp: ", exp)
    if not exp or current_ts > exp:
        db.query(Token).filter(Token.token == token_str).delete()
        db.commit()
        raise HTTPException(status_code=401, detail="Token expired")
    
    # Check inactivity: if last_activity is older than 60 minutes.
    last_activity_ts = token_data.get("last_activity")
    if last_activity_ts:
        inactivity = datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(last_activity_ts)
        if inactivity > datetime.timedelta(minutes=180):  # 60 minutes of inactivity
            # Log out the user by deleting the token.
            db.query(Token).filter(Token.token == token_str).delete()
            db.commit()
            raise HTTPException(status_code=401, detail="Logged out due to inactivity")
    
    # Update token's last_activity timestamp.
    new_last_activity = datetime.datetime.utcnow()
    db.query(Token).filter(Token.token == token_str).update({"last_activity": new_last_activity})
    db.commit()
    
    # Retrieve the user.
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    try:
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        print("user obj: ", user.id)
    except Exception:
        raise HTTPException(status_code=401, detail="User not found")
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Retrieve the user's role.
    role_id = token_data.get("role_id")
    if not role_id:
        raise HTTPException(status_code=401, detail="Token missing role information")
    role_obj = db.query(Role).filter(Role.id == UUID(role_id)).first()
    if not role_obj:
        raise HTTPException(status_code=400, detail="Unable to fetch user privileges")
    
    return {
        "id":user.id,
        "user": user,
        "role": role_obj.name,
        "permissions": role_obj.permissions
    }


async def get_current_user_for_others(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
) -> dict:
    """
    Retrieves the current user based on the provided JWT token.
    - Checks that the token is valid and not expired.
    - Checks inactivity (15 minutes threshold) and logs out if exceeded.
    - Updates the token's last_activity timestamp on each request.
    - Retrieves the user and associated role data.
    
    Returns a dictionary with keys:
      "user": the User model instance,
      "role": the user's role name,
      "permissions": the permissions from the user's role.
    """
    token_str = credentials.credentials
    print("get_current_user: ", token_str)
    token_data = await global_security.decode_token(token_str)
    print("token_data: ", token_data)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Check token expiration.
    current_ts = datetime.datetime.utcnow().timestamp()
    exp = token_data.get("exp")
    print("exp: ", exp)
    if not exp or current_ts > exp:
        db.query(Token).filter(Token.token == token_str).delete()
        db.commit()
        raise HTTPException(status_code=401, detail="Token expired")
    
    # Check inactivity: if last_activity is older than 60 minutes.
    last_activity_ts = token_data.get("last_activity")
    if last_activity_ts:
        inactivity = datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(last_activity_ts)
        if inactivity > datetime.timedelta(minutes=60):  # 60 minutes of inactivity
            # Log out the user by deleting the token.
            db.query(Token).filter(Token.token == token_str).delete()
            db.commit()
            raise HTTPException(status_code=401, detail="Logged out due to inactivity")
    
    # Update token's last_activity timestamp.
    new_last_activity = datetime.datetime.utcnow()
    db.query(Token).filter(Token.token == token_str).update({"last_activity": new_last_activity})
    db.commit()
    
    # Retrieve the user.
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    try:
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        print("user obj: ", user.id)
    except Exception:
        raise HTTPException(status_code=401, detail="User not found")
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user
    # # Retrieve the user's role.
    # role_id = token_data.get("role_id")
    # if not role_id:
    #     raise HTTPException(status_code=401, detail="Token missing role information")
    # role_obj = db.query(Role).filter(Role.id == UUID(role_id)).first()
    # if not role_obj:
    #     raise HTTPException(status_code=400, detail="Unable to fetch user privileges")
    
    # return {
    #     "id":user.id,
    #     "user": user,
    #     "role": role_obj.name,
    #     "permissions": role_obj.permissions
    # }

async def _decode_and_validate_token(
    token_str: str,
    db: Session
) -> Dict[str, Any]:
    """
    Core logic from your get_current_user, minus FastAPI-specific Depends.
    Decodes the JWT, checks exp + inactivity, updates last_activity,
    and returns the raw token payload.
    """
    token_data = await global_security.decode_token(token_str)
    if not token_data:
        raise HTTPException(401, "Invalid token")

    now_ts = datetime.utcnow().timestamp()
    exp    = token_data.get("exp")
    if not exp or now_ts > exp:
        db.query(Token).filter(Token.token == token_str).delete()
        db.commit()
        raise HTTPException(401, "Token expired")

    last_act = token_data.get("last_activity")
    if last_act and (datetime.utcnow() - datetime.fromtimestamp(last_act)) > datetime.timedelta(minutes=60):
        db.query(Token).filter(Token.token == token_str).delete()
        db.commit()
        raise HTTPException(401, "Logged out due to inactivity")

    # update last_activity
    db.query(Token).filter(Token.token == token_str).update(
        {"last_activity": datetime.utcnow()}
    )
    db.commit()

    return token_data

def require_permissions(required: List[str]):
    """
    Dependency generator to enforce that the current user has at least one
    of the permissions in the 'required' list.
    
    Usage: Inject as a dependency on protected endpoints.
    """
    def permission_checker(current_user: Dict = Depends(get_current_user)) -> Dict:
        user_permissions = current_user.get("permissions") or []
        if not any(perm in user_permissions for perm in required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Missing at least one of: {', '.join(required)}"
            )
        return current_user
    return permission_checker

def require_hr_dashboard(user: User = Depends(get_current_user)):
    print("\n\n\nuser in require hr dashboard permission in utils.security::: ", user)
    print(f"\n\n perm then:: {user.role}")
    """
    Checks user.role.permissions for 'hr:dashboard', supporting both:
    - list of strings:    ["hr:dashboard", ...]
    - dict of flags:      { "hr:dashboard": true, ... }
    """
    perms = user.role.permissions or {}
    allowed = False

    if isinstance(perms, dict):
        allowed = bool(perms.get("hr:dashboard"))
    elif isinstance(perms, list):
        allowed = "hr:dashboard" in perms

    if not allowed:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return user


def get_token_data_by_user_id( userid: UUID, db: Session = Depends(get_db)) -> dict:
    """
    Retrieves the token data based on the logged-in User ID.
    

    Returns a dictionary with keys:
    "organization_id": the User's organization ID,
    "token": the generated token,
    "expiration_period": the generated token expiration period.
    "login_option": the authentication option chosen by the account holder during authentication
    "last_activity": timestamp of the last|latest activity perofrmed by the account holder after logging in. 
    """
    
    token = db.query(Token).filter(Token.user_id == userid).first()

    if token:
        return {
                "organization_id": token.organization_id,
                "token": token.token,
                "expiration_period": token.expiration_period,
                "login_option": token.login_option,
                "last_activity": token.last_activity
            }
    else:
        raise HTTPException(status_code=400, detail=f"No existing Token Data for the User with ID '{userid}'")
    




def ensure_hr_dashboard_ws(user: User):
    """
    Raise WebSocketDisconnect if user lacks 'hr:dashboard' permission.
    """
    print("\n\nuser object:: ", user)
    perms = user.role.permissions or {}
    ok = False
    if isinstance(perms, dict):
        ok = bool(perms.get("hr:dashboard"))
    elif isinstance(perms, list):
        ok = "hr:dashboard" in perms
    if not ok:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)
    return True