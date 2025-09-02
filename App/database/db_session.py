
# App/database/db_session.py

from sqlalchemy import create_engine, Column, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.pool import NullPool
import os
import uuid
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Load environment variables from .env
load_dotenv()

# Database URL
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:password@localhost/records_db"
SQLALCHEMY_ASYNC_DATABASE_URL = os.getenv("ASYNC_DATABASE_URL") or "postgresql+asyncpg://postgres:password@localhost/records_db"

if not SQLALCHEMY_DATABASE_URL or not SQLALCHEMY_ASYNC_DATABASE_URL:
    raise ValueError("Database URLs are not configured. Check the environment variables.")

# Sync Engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Async Engine
async_engine = create_async_engine(
    SQLALCHEMY_ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    poolclass=NullPool,
)

# Session Makers
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# # Configure your async database URL
# DATABASE_URL = "postgresql+asyncpg://username:password@host/dbname"
# engine = create_async_engine(DATABASE_URL, echo=False)
# async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

 

# Declarative Base
Base = declarative_base()


# Base Model
class BaseModel(Base):
    __abstract__ = True

    id = Column(SQLUUID(as_uuid=True), primary_key=True, index=True, nullable=False, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by = Column(SQLUUID(as_uuid=True), nullable=True)  # Tracks user who created the record
    updated_by = Column(SQLUUID(as_uuid=True), nullable=True)  # Tracks user who last updated the record


# Dependency for Sync Database Session
def get_db():
    """Provides a synchronous database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# **NEW** async generator function for FastAPI
async def get_async_db():
    """
    Provides an AsyncSession, properly `yield`ed for FastAPI dependency injection.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except:
            await session.rollback()
            raise
        finally:
            await session.close()


# Dependency for Async Database Session
# @asynccontextmanager
# async def get_async_db():
#     """Provides an asynchronous database session."""
#     async with AsyncSessionLocal() as session:
#         try:
#             yield session
#         except Exception as e:
#             await session.rollback()
#             raise e
#         finally:
#             await session.close()

# async def get_db():
#     async with async_session() as session:
#         yield session

from Models.Tenants.organization import Organization
from Models.Tenants.role import Role
from Models.models import User

# Utility for Schema Migration or Testing
def temp_db():
    """Creates temporary PostgreSQL database for testing or development purposes."""
    # Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("PostgreSQL database Tables created.")



