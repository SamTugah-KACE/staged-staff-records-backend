from fastapi import APIRouter, Depends, HTTPException, UploadFile, BackgroundTasks, Query, Form
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict
from uuid import UUID
from database.db_session import get_db, get_async_db  # Dependency injection
from Models.Tenants.organization import Organization
from Models.models import AuditLog, User
from Schemas.schemas import OrganizationCreateSchema, OrganizationSchema # OrganizationUpdateSchema, OrganizationReadSchema
from Crud.crud import organization_crud
# from Crud.base import CRUDBase
# from Crud.async_base import CRUDBase as AsyncCRUDBase


router = APIRouter()

# CRUDBase instances
# organization_crud = CRUDBase(Organization, AuditLog)

