# src/crud/employee_data_input.py
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
import uuid
from sqlalchemy import and_, func, text, inspect, update
from sqlalchemy.orm import Session, joinedload
from fastapi import Depends, HTTPException, UploadFile
import json
from Service.storage_service import BaseStorage
from Models.Tenants.organization import Organization
from Service.sms_service import BaseSMSService
from Utils.sms_utils import get_sms_service
from Models.models import Employee, EmployeeDataInput, RequestStatus, User
from Schemas.schemas import (
    EmployeeDataInputCreate,
    EmployeeDataInputUpdate,
    EmployeeDataInput as EmployeeDataInputSchema,
)
from Service.apply_data_input import apply_data_input
from Utils.storage_utils import get_storage_service
from Utils.util import get_organization_acronym
from Models import models
import logging
from sqlalchemy.dialects.postgresql import JSONB
from pprint import pformat
from notification.socket import manager
from Utils.util import extract_attachments
logger = logging.getLogger(__name__)

class RequestStatus(str, Enum):
    Pending = "Pending"
    Approved = "Approved"
    Rejected = "Rejected"



    

def create_data_input(
    db: Session,
    *,
    organization_id:str,
    obj_in: EmployeeDataInputCreate,
    files: List[UploadFile],
    storage: BaseSMSService = Depends(get_storage_service)
) -> EmployeeDataInput:
    # merge file uploads into obj_in.data
    data = dict(obj_in.data)
    organization_id = UUID(organization_id)
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail=f"{organization_id} Not found")

    emp = db.query(Employee).filter(Employee.id == obj_in.employee_id, Employee.organization_id == organization_id).first()
    print("emp", emp)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee {obj_in.employee_id} not found in organization {org.name}")
    if files:
        file_dicts = []
        for f in files:
            content = f.file.read()
            file_dicts.append({
                "filename": f.filename,
                "content": content,
                "content_type": f.content_type,
            })
        
        urls = storage.upload(file_dicts, folder=f"organizations/{get_organization_acronym(org.name)}/{obj_in.data_type}")
        data.update(urls)

    db_obj = EmployeeDataInput(
        employee_id=obj_in.employee_id,
        data=data,
        request_type=obj_in.request_type,
        data_type=obj_in.data_type,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


# async def create_or_update_data_input(
#     db: Session,
#     *,
#     organization_id:str,
#     obj_in: EmployeeDataInputCreate,
#     files: List[UploadFile],
#     storage: BaseStorage = Depends(get_storage_service)
# ) -> EmployeeDataInput:
#     # 1️⃣ Validate organization
#     organization_id = UUID(organization_id)
#     org = db.query(Organization).get(organization_id)
#     if not org:
#         raise HTTPException(404, f"Organization {obj_in.organization_id} not found")

#     # 2️⃣ Validate employee belongs to that organization
#     emp = (
#         db.query(Employee)
#           .filter_by(id=obj_in.employee_id, organization_id=obj_in.organization_id)
#           .one_or_none()
#     )
#     if not emp:
#         raise HTTPException(404, f"Employee {obj_in.employee_id} not in organization {org.id}")

#     # 3️⃣ Merge any uploaded files into the data dict
#     # data = dict(obj_in.data)
#     data = obj_in.data.copy()
#     print("crud files: ", files)
#     if files:
#         uploads = []
#         for f in files:
#             print("f in files: ", f)
#             # content = await f.read() if hasattr(f, "read") and f.read.__code__.co_flags & 0x80 else f.file.read()
            
#             content = await f.read() if hasattr(f, "read") else f.file.read()
#             print("content", content)
#             # If the file is a path, read it
#             # If the file is a stream, read it
#             uploads.append({
#                 "filename": f.filename,
#                 "content": content,
#                 "content_type": f.content_type or "application/octet-stream",
#             })
#         urls = storage.upload(uploads, folder=f"organizations/{get_organization_acronym(org.name)}/{obj_in.data_type}")
#         print("\n\n\nurls: ", urls)
#         # Merge URLs into the data dict
#         data.update({"certificate_path":urls})
#         print("data after update{'certificate_path':urls}: ", data)
       
#     # 4️⃣ Try to find an existing PENDING request for this triple
#     existing = (
#         db.query(EmployeeDataInput)
#           .filter_by(
#               employee_id=obj_in.employee_id,
#               organization_id=obj_in.organization_id,
#               data_type=obj_in.data_type,
#               status=RequestStatus.Pending.value
#           )
#           .one_or_none()
#     )

#     if existing:
#         existing.data = {}
#         # Overwrite its data, bump timestamp, leave request_type as-is
#         existing.data = data
#         existing.request_date = func.now()
#         db.add(existing)
#         db.commit()
#         db.refresh(existing)
#         return existing

#     # 5️⃣ Otherwise insert a brand-new pending record
#     new_record = EmployeeDataInput(
#         employee_id    = obj_in.employee_id,
#         organization_id= obj_in.organization_id,
#         data           = obj_in.data,
#         request_type   = obj_in.request_type,
#         data_type      = obj_in.data_type,
#         status         = RequestStatus.Pending.value
#     )
#     db.add(new_record)
#     db.commit()
#     db.refresh(new_record)
#     return new_record

# ─── CONFIGURATION ────────────────────────────────────────────────────────────────

# For each data_type: which SQLAlchemy model, how to map incoming keys → model columns,
# which single‐string column holds the “primary” file URL, and which JSONB column to dump everything else.
DATA_TYPE_CONFIG = {
    "academic_qualifications": {
        "model": models.AcademicQualification,
        "key_map": {
            "institution": "institution",
            "degree":      "degree",
            "year_obtained": "year_obtained",
        },
        "file_column":    "certificate_path",
        "details_column": "details",
    },
    "professional_qualifications": {
        "model": models.ProfessionalQualification,
        "key_map": {
            "institution":         "institution",
            "qualification_name":  "qualification_name",
            "year_obtained":       "year_obtained",
        },
        "file_column":    "license_path",
        "details_column": "details",
    },
    "employment_history": {
        "model": models.EmploymentHistory,
        "key_map": {
            "job_title":  "job_title",
            "company":    "company",
            "start_date": "start_date",
            "end_date":   "end_date",
        },
        "file_column":    "documents_path",
        "details_column": "details",
    },
    "employees": {
        "model": models.Employee,
        "key_map": {
            "first_name":      "first_name",
            "middle_name":     "middle_name",
            "last_name":       "last_name",
            "title":           "title",
            "gender":          "gender",
            "date_of_birth":   "date_of_birth",
            "marital_status":  "marital_status",
            "email":           "email",
            "contact_info":"contact_info",
            "hire_date":       "hire_date",
            "termination_date":"termination_date",
            
        },
        "file_column":    "profile_image_path",
        "details_column": "custom_data",
    },
    "employee_payment_details":{
        "model": models.EmployeePaymentDetail,
        "key_map":{
            "payment_mode": "payment_mode",
            "bank_name": "bank_name",
            "account_number": "account_number",
            "mobile_money_provider": "mobile_money_provider",
            "wallet_number": "wallet_number",
            "is_verified": "is_verified",
            "additional_info":"additional_info",
        },
        "file_column": "",
        "details_column": "",
    },
    "emergency_contacts":{
     "model": models.EmergencyContact,
     "key_map":{
         "name":"name",
         "relation":"relation",
         "emergency_phone":"emergency_phone",
         "emergency_address":"emergency_address",
         "details":"details",
     },
     "file_column":"",
     "details_column": "",
    },
    "next_of_kin":{
        "model": models.NextOfKin,
    "key_map":{
        "name":"name",
        "relation": "relation",
        "nok_phone":"nok_phone",
        "nok_address": "nok_address",
        "details": "details",
    },
    "file_column": "",
    "details_column": "",
    }
    # … add other data_types here …
}

# ─── UPSET FUNCTION ────────────────────────────────────────────────────────────────

async def create_or_update_data_input(
    *,
    db: Session,
    organization_id: str,
    obj_in: EmployeeDataInputCreate,
    files: List[UploadFile],
    storage: BaseStorage = Depends(get_storage_service),
) -> models.EmployeeDataInput:

    # 1️⃣ Validate organization & employee membership
    org_uuid = UUID(organization_id)
    org = db.query(models.Organization).get(org_uuid)
    if not org:
        raise HTTPException(404, f"Organization {organization_id} not found")

    emp = (
        db.query(models.Employee)
          .filter_by(
             id=obj_in.employee_id,
             organization_id=obj_in.organization_id
          )
          .one_or_none()
    )
    if not emp:
        raise HTTPException(404, f"Employee {obj_in.employee_id} not in org {organization_id}")

    # 2️⃣ Look up config for this data_type
    cfg = DATA_TYPE_CONFIG.get(obj_in.data_type)
    if cfg is None:
        raise HTTPException(400, f"Unsupported data_type: {obj_in.data_type}")

    # 3️⃣ Prepare payload & column_data
    incoming: Dict[str, Any] = dict(obj_in.data)  # shallow copy
    column_data: Dict[str, Any] = {}

    # 3a) Map known scalar fields
    for in_key, col_name in cfg["key_map"].items():
        if in_key in incoming:
            column_data[col_name] = incoming.pop(in_key)

    # 3b) Handle file uploads
    if files:
        uploads = []
        for f in files:
            content = await f.read() if hasattr(f, "read") else f.file.read()
            # If the file is a path, read it
            # If the file is a stream, read it
            # If the file is a stream, read it
            uploads.append({
                "filename":     f.filename,
                "content":      content,
                "content_type": f.content_type or "application/octet-stream",
            })
        folder=f"organizations/{get_organization_acronym(org.name)}/{obj_in.data_type}"
        urls = storage.upload(uploads, folder=folder)
        logger.debug("Uploaded files → URLs: %r", urls)

        # first URL → single‐string column
        # first_url = urls
        # column_data[cfg["file_column"]] = first_url

        # # any extras → push into details_column.files array
        # if len(urls) > 1:
        #     incoming.setdefault(cfg["details_column"], {})
        #     incoming[cfg["details_column"]].setdefault("files", [])
        #     incoming[cfg["details_column"]]["files"].extend(urls[1:])

        # 2️⃣ Always store the full list
        # If your SQL column is JSONB, just save the list.
        # If it’s a String, JSON‐dump it:
        file_col = cfg["file_column"]
        model_col = getattr(cfg["model"], file_col).type

        if isinstance(model_col, JSONB):
            # JSONB → store list directly
            column_data[file_col] = urls
        else:
            # String → store JSON‐encoded array
            column_data[file_col] = json.dumps(urls)

    # 3c) Any remaining keys → details_column JSONB
    if incoming:
        column_data[cfg["details_column"]] = incoming

    # 4️⃣ Upsert a pending EmployeeDataInput record
    existing = (
        db.query(models.EmployeeDataInput)
          .filter_by(
            employee_id    = obj_in.employee_id,
            organization_id= obj_in.organization_id if isinstance(obj_in.organization_id, UUID) else org_uuid,
            data_type      = obj_in.data_type,
            status         = RequestStatus.Pending.value
          )
          .one_or_none()
    )

    if existing:
        # overwrite data
        existing.data           = column_data
        existing.request_date   = func.now()
        existing.request_type   = obj_in.request_type
        db.add(existing)
        db.commit()
        db.refresh(existing)
        record = existing
        event_type = "updated_input"
        # return existing
    else:
        # create new record
        # 5️⃣ Otherwise create new
        new_input = models.EmployeeDataInput(
            employee_id    = obj_in.employee_id,
            organization_id= obj_in.organization_id if isinstance(obj_in.organization_id, UUID) else org_uuid,
            data_type      = obj_in.data_type,
            request_type   = obj_in.request_type,
            status         = RequestStatus.Pending.value,
            data           = column_data
        )
        db.add(new_input)
        db.commit()
        db.refresh(new_input)
        record = new_input
        event_type = "new_input"
    
    emp = db.query(Employee).filter(Employee.id == obj_in.employee_id).first()

    # user_obj =  db.query(User).filter(User.email == emp.email).first()

    user_obj = (
            db.query(User)
              .options(joinedload(User.role))
              .filter(
                  and_(
                      User.organization_id == organization_id,
                      User.email == emp.email
                  )
              ).first()
    )

    
    full_name = " ".join(filter(None, [emp.title if emp.title != "Other" else ''.strip(), emp.first_name, emp.middle_name if emp.middle_name else ''.strip(), emp.last_name]))
    role_name = user_obj.role.name if user_obj and user_obj.role else "N/A"

    
    # Build the minimal payload
    out = {
        "id":           str(record.id),
        "Account Name":  full_name,
        "Role":         role_name,
        "Data":         record.data,
        "Attachments":  extract_attachments(record.data or {}),
        "Issues":       "Request Approval",
        "Actions":      "Pending",
    }

    # Broadcast immediately to this org
    await manager.broadcast(
      str(record.organization_id),
      json.dumps({ "type": event_type, "payload": out })
    )
    # return new_input
    return record
        

    



def get_data_input(db: Session, id: str) -> Optional[EmployeeDataInput]:
    return db.query(EmployeeDataInput).filter(EmployeeDataInput.id == id).first()


def get_data_inputs_by_employee(db: Session, employee_id: str) -> List[EmployeeDataInput]:
    return db.query(EmployeeDataInput).filter(EmployeeDataInput.employee_id == employee_id).all()   

def get_data_inputs_by_employee_order_by_date(db: Session, employee_id: UUID) -> List[EmployeeDataInput]:
    return (
        db.query(EmployeeDataInput)
          .filter(EmployeeDataInput.employee_id == employee_id)
          .order_by(EmployeeDataInput.request_date.desc())
          .all()
    )



def get_data_inputs(db: Session, skip: int = 0, limit: int = 100) -> List[EmployeeDataInput]:
    return db.query(EmployeeDataInput).offset(skip).limit(limit).all()

def update_data_input(
    db: Session,
    *,
    id: str,
    obj_in: EmployeeDataInputUpdate
) -> EmployeeDataInput:
    db_obj = get_data_input(db, id)
    
    if not db_obj:
        raise HTTPException(status_code=404, detail="Not found")

    #get organization_id from the db_obj
    # organization_id = db_obj.organization_id

    old_status = db_obj.status
    update_data = obj_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    
    # If we just transitioned into Approved or Rejected…
    new_status = db_obj.status

    if old_status != RequestStatus.Approved and db_obj.status == RequestStatus.Approved:
        try:
            # 1️⃣ apply only on approval
            if new_status == RequestStatus.Approved:
                apply_data_input(db, db_obj)
                       
            # ← apply_data_input must NOT commit internally
            # apply_data_input(db, db_obj)

            # 2️⃣ then delete the temporary input in either case
            # delete the temporary input row
            db.delete(db_obj)
            # one final commit for handler + delete
            db.commit()
        except Exception:
            db.rollback()
            raise

    # at this point, the transaction is committed
    return db_obj

def delete_data_input(db: Session, id: str) -> EmployeeDataInput:
    db_obj = get_data_input(db, id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(db_obj)
    db.commit()
    return db_obj
