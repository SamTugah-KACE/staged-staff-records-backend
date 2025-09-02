import datetime
from typing import Optional, Union
from uuid import UUID
from Crud.auth import authenticate_user, get_current_user, get_token_data_by_user_id
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect, UploadFile, Query, BackgroundTasks, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database.db_session import get_db
from Models.models import User, Token 
from notification.socket import manager






security = HTTPBearer()





router = APIRouter()




# --------------------------------------------------------------------
# fetch tourGuide status from User model using organization_id and user_id
# @router.get("/tour_guide_status", tags=["Auth"])
# def get_tour_guide_status(
#     organization_id: UUID,
#     user_id: UUID,
#     token: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Fetches the tour guide status for a given user in a specific organization.
    
#     Returns:
#         A dictionary containing the tour guide status.
#     """
#     if not token or not token["user"]:
#         raise HTTPException(status_code=401, detail="Unauthorized")
#     user = db.query(User).filter(
#         User.id == user_id,
#         User.organization_id == organization_id
#     ).first()
    
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     return {"tour_guide_status": user.tour_guide_status}



# --------------------------------------------------------------------
# LOGOUT ENDPOINT (Clears Token Data)
# --------------------------------------------------------------------
@router.post("/logout", tags=["Auth"])
async def logout_user(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Logs out the current user by deleting their token from the database.
    """
    token_str = credentials.credentials
    print("logout current user: ", current_user)
    db.query(Token).filter(
        Token.token == token_str,
        Token.user_id == current_user["id"],
        Token.organization_id == current_user["user"].organization_id).delete()
    db.commit()

    # close all WS for this org/user
    await manager.unregister_user(str(current_user["user"].organization_id), str(current_user["id"]))
    return {"detail": "Logged out successfully"}



# --------------------------------------------------------------------
# LOGIN API ENDPOINT
# --------------------------------------------------------------------
@router.post("/login",  response_model=dict, tags=["Auth"])
async def login_endpoint(
    background_task: BackgroundTasks,
    username: str = Form(...),
    password: Optional[str] = Form(None),
    # facial_image: Optional[UploadFile] = File(None),
    facial_image: Optional[Union[UploadFile, str]] = File(None),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db)
): 
    """
    Login API that supports two-way authentication.
    
    Usage examples:
      - Traditional login: Provide 'username' and 'password'.
      - Facial login: Provide 'username' and a 'facial_image' file.
    
    Returns the user details, token, dashboard URL, and other relevant info.
    """

     # If facial_image is an empty string, override it with None.
    if isinstance(facial_image, str) and facial_image.strip() == "":
        facial_image = None

    result = await authenticate_user(background_task, db, username, password, facial_image, request, response)
    return result

# --------------------------------------------------------------------
# RATE LIMITER LOGS ENDPOINT
# --------------------------------------------------------------------
@router.get("/logs")
def get_logs(
    organization_id: UUID,
    log_date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to today)")
):
    """
    Retrieves the log file for the specified organization and date.
    If no date is provided, returns the logs for the current date.
    """
    if log_date is None:
        log_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    log_file_path = f"logs/{organization_id}/{log_date}.log"
    try:
        with open(log_file_path, "r") as f:
            log_content = f.read()
        return {"organization_id": str(organization_id), "date": log_date, "logs": log_content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Log file not found")



@router.get("/token")
def get_tokens_by_User_Id(
    user_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Retrieves the token data based on the logged-in User ID.
    

    Returns a dictionary with keys:
    "organization_id": the User's organization ID,
    "token": the generated token,
    "expiration_period": the generated token expiration period.
    "login_option": the authentication option chosen by the account holder during authentication
    "last_activity": timestamp of the last|latest activity perofrmed by the account holder after logging in. 
    """
    result =  get_token_data_by_user_id(user_id, db)
    return result