import secrets
from fastapi import HTTPException, WebSocketDisconnect, status, Depends
from fastapi.security import OAuth2PasswordBearer
from Models import models
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from jose import jwt, JWTError, ExpiredSignatureError
from typing import Any, Dict, Optional
import logging
from .config import DevelopmentConfig
from database.db_session import get_db




# Offload blocking operations to a threadpool in an async context.
from starlette.concurrency import run_in_threadpool

settings = DevelopmentConfig()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)



pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Try to use cachetools for TTL caching; if unavailable, fall back to a plain dict.
try:
    from cachetools import TTLCache
except ImportError:
    TTLCache = None



class Security:
    def __init__(self, secret_key: str, algorithm: str, token_expire_minutes: int = 480): #, length:int=8#):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.token_expire_minutes = token_expire_minutes
        # self.length =length
        # Setup a TTL cache for decoded tokens if possible
        if TTLCache:
            self.token_cache = TTLCache(maxsize=1024, ttl=token_expire_minutes * 60)
        else:
            self.token_cache = {}



    # @staticmethod
    # def hash_password(password: str) -> str:
    #     return pwd_context.hash(password)

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    # @staticmethod
    # def get_user(organization_id: Any,  db: Session):
    #     try:
    #         user = db.query(User).filter(User.organization_id==organization_id).first()
    #         if not user:
    #             return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not Found")
    #     except Exception as e:
    #         logging.DEBUG(f"Error getting user data: {str(e)}")
    #         raise e
    

    # Secure Token Generation
    def generate_random_string(length:int):
        
        characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()"
        return "".join(secrets.choice(characters) for _ in range(length))
    
    def generate_random_char(length:int):
        characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return "".join(secrets.choice(characters) for _ in range(length))

    # @staticmethod 
    # def verify_password(plain_password, hashed_password):
    #     return pwd_context.verify(plain_password, hashed_password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
        
    # @staticmethod 
    # def get_password_hash(password='password'):
    #     return pwd_context.hash(password)

    def get_password_hash(self, password: str = 'password') -> str:
        return pwd_context.hash(password)
    

    # @staticmethod
    # def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    #     to_encode = data.copy()
    #     if expires_delta:
    #         expire = datetime.now(timezone.utc) + expires_delta
    #     else:
    #         expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    #     to_encode.update({"exp": expire})
    #     encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    #     return encoded_jwt

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    

    def generate_token(self, data: Dict[str, Any], expires_in: int = 28800) -> str:
        """
        Generates a JWT token that includes tenant-specific data (e.g., organization_id).
        """
        to_encode = data.copy()
        expiration = datetime.utcnow() + timedelta(seconds=expires_in)
        to_encode.update({"exp": expiration})
        token = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return token
    

    # Generate reset password token function
    # @staticmethod
    # def generate_reset_password_token(expires: int = None):
    #     if expires is not None:
    #         expires = datetime.now(timezone.utc) + expires
    #     else:
    #         expires = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    #     to_encode = {"exp": expires}
    #     encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, settings.ALGORITHM)
    #     return encoded_jwt

    def generate_reset_password_token(self, expires: Optional[timedelta] = None) -> str:
        if expires is not None:
            expire = datetime.now(timezone.utc) + expires
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.token_expire_minutes)
        to_encode = {"exp": expire}
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def get_current_user(self, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise credentials_exception
        return user


    async def get_current_user_ws(self, token: str, db: Session):
        """
        Decode JWT 'sub' → user.id, fetch User.
        Raises if invalid.
        """
        try:
            print(f"\n\nTOKEN: {token}   \n\n")
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            print("payload:: ", payload)
            user_id: str = payload.get("user_id")
            print("user_id: ", user_id)
            if not user_id:
                raise JWTError()
        except ExpiredSignatureError:
            logger.warning("WebSocket token expired")
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)
        except JWTError:
            logger.error("WebSocket token invalid")
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)

        user = db.query(models.User).filter(models.User.id == user_id).first()
        print("user: ", user)
        # If user not found, raise WebSocketDisconnect with policy violation code
        if not user:
            logger.error(f"WebSocket user not found: {user_id}")
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)
        logger.debug(f"WebSocket authenticated user: {user.username} (ID: {user.id})")
        # Return the user object if found
        return user

    # @staticmethod
    # def decode_token(token_str: str):
    #     try:
        
    #         payload = jwt.decode(token=token_str, key=settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    #         print("\n\njwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]):\n", jwt.decode(token_str, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]))
    #         print("decode payload: ", payload)
    #         return payload
    #     except JWTError as e:
    #         print("\n\nerror: ",e)
    #         return None

    async def decode_token(self, token_str: str) -> Optional[Dict[str, Any]]:
        """
        Asynchronously decodes a JWT token using a threadpool to offload the synchronous operation.
        Uses caching to speed up repeated decodes.
        """
        if token_str in self.token_cache:
            logger.debug("Returning cached token payload")
            return self.token_cache[token_str]

        try:
            payload = await run_in_threadpool(
                jwt.decode, token_str, self.secret_key, algorithms=[self.algorithm]
            )
            logger.debug(f"Decoded token payload: {payload}")
            self.token_cache[token_str] = payload
            return payload
        except JWTError as e:
            logger.error(f"JWT decoding error: {e}")
            return None

    async def is_token_valid(self, token_str: str) -> bool:
        try:
            # offload to threadpool, but don’t raise on ExpiredSignatureError
            await run_in_threadpool(jwt.decode, token_str, self.secret_key, [self.algorithm])
            return True
        except ExpiredSignatureError:
            print(f"\nis_token_valid returned with: {ExpiredSignatureError}")
            return False
        except JWTError:
            print(f"is_token_valid returned with: {JWTError}")
            return False
        
    
    async def is_ws_token_valid(self, token_str: str, db: Session) -> bool:
        """
        1) Decode JWT (catches ExpiredSignatureError).
        2) Verify a matching Token row still exists & expiration_period > now.
        """
        try:
            # offload to threadpool but swallow ExpiredSignatureError:
            payload = await run_in_threadpool(jwt.decode, token_str, self.secret_key, [self.algorithm])
            print(f"\nwell token payload is still live:: {payload}")
        except (ExpiredSignatureError, JWTError):
            return False

        # check DB record
        tok = db.query(models.Token).filter(models.Token.token == token_str).first()

        print(f"\ntoken expiration period::  {tok.expiration_period if tok else tok} \t\t time now {datetime.utcnow()}")
        
        if not tok or tok.expiration_period < datetime.utcnow():
            return False

        return True