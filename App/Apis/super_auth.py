# Apis/routers/superadmin_auth.py
from datetime import datetime
from fastapi import APIRouter, Form, Request, Response, HTTPException, Depends, BackgroundTasks, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from Crud.sup_dependencies import get_current_superadmin, get_refresh_token
from Schemas.schemas import TokenResponse
from Utils.sup_security import create_access_token, create_refresh_token, verify_password
from Crud.auth import get_current_user
from database.db_session import get_async_db, get_db
from Models.superadmin import RefreshToken, SuperAdmin
from Utils.security import Security
from Utils.config import ProductionConfig 
from cachetools import TTLCache
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession


settings = ProductionConfig()
global_security = Security(secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM, token_expire_minutes=480)

router = APIRouter(prefix="/superadmin/auth", tags=["SuperAdminAuth"])



# Store token<->user_id mapping for 10 minutes (or whatever timeout you prefer)
temporary_dashboard_links = TTLCache(maxsize=1000, ttl=600)  # 10 mins


@router.post("/login", response_model=dict)
def superadmin_login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    security_key: str = Form(...),
    db: Session = Depends(get_db)
):
    sa = db.query(SuperAdmin).filter_by(username=username, is_active=True).first()
    if not sa or not global_security.verify_password(password, sa.hashed_password):
        raise HTTPException(401, "Invalid username or password")

    if not global_security.verify_password(security_key, sa.security_key_hash):
        raise HTTPException(401, "Invalid security key")

    token = global_security.create_access_token({"sub": str(sa.id), "role": "super_admin"})
    
    # Set the JWT as an HttpOnly, Secure cookie
    # Here we name the cookie "access_token"; adjust domain/path as needed for production
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,        # only send over HTTPS in production
        samesite="lax",     # prevents CSRF, adjust per your needs
        max_age=60 * 60 * 8 # e.g. 8 hours
    )

    # Generate unique dashboard UUID
    dashboard_id = str(uuid4())
    temporary_dashboard_links[dashboard_id] = sa.id
    
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": sa.username,
        "dashboard_url": f"/dev/dashboard/{dashboard_id}",
    }



@router.post("/token", response_model=TokenResponse)
async def login_for_tokens(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    
    db: AsyncSession = Depends(get_async_db),
):
    # 1) verify credentials
    result = await db.execute(
        select(SuperAdmin).where(SuperAdmin.username == form_data.username)
    )
    admin = result.scalars().first()
    if not admin or not verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # 2) create access & refresh tokens
    access_token = create_access_token(subject=str(admin.id))
    refresh_token, expires = create_refresh_token()

    db.add(
        RefreshToken(
            superadmin_id=admin.id,
            token=refresh_token,
            expires_at=expires,
        )
    )
    await db.commit()

    # 3) set cookie
    # set cookie with max_age instead of naive expires
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    response.set_cookie(
        settings.COOKIE_NAME,
        refresh_token,
        secure=settings.COOKIE_SECURE,
        httponly=settings.COOKIE_HTTPONLY,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.COOKIE_PATH,
        max_age=max_age
        # expires=expires,
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    response: Response,
    refresh_token: str = Depends(get_refresh_token),
    db: AsyncSession = Depends(get_async_db),
):
    # verify token exists and not expired
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == refresh_token,
            RefreshToken.expires_at > datetime.utcnow(),
        )
    )
    rt = result.scalars().first()
    if not rt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # issue new access token
    access_token = create_access_token(subject=str(rt.superadmin_id))
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_superadmin(
    response: Response,
    request: Request,
    current_admin = Depends(get_current_superadmin),
    refresh_token: str = Depends(get_refresh_token),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Invalidate the current session's refresh token and clear cookie.
    """
    result = await db.execute(
        delete(RefreshToken).where(
            RefreshToken.superadmin_id == current_admin.id,
            RefreshToken.token == refresh_token,
        )
    )
    await db.commit()
    response.delete_cookie(settings.COOKIE_NAME, path=settings.COOKIE_PATH)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/dashboard/{dashboard_id}")
def protected_dashboard(
    dashboard_id: str,
    token: str = Depends(get_current_user),  # Assuming you have a dependency to get the current user
):
    if dashboard_id not in temporary_dashboard_links:
        raise HTTPException(403, "Invalid or expired dashboard link")

    user_id = temporary_dashboard_links[dashboard_id]
    if str(token.get("sub")) != str(user_id):
        raise HTTPException(403, "You are not authorized to access this dashboard.")

    # Serve dashboard or return JSON data here
    return {"message": "Welcome to your dashboard"}

