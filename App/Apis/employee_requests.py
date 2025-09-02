# src/api/employee_data_inputs.py
import json
from typing import List
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, status, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload
from Service.employee_aggregator import get_employee_full_record
from Crud.auth import ensure_hr_dashboard_ws, get_current_user
from .deps_ws import get_current_user_ws
from Models.models import Employee, EmployeeDataInput, RequestStatus, User
from Service.storage_service import BaseStorage
from database.db_session import get_db
from Crud import employee_data_input
from Schemas import schemas
# from Utils.security import get_current_active_user, get_current_active_admin
from Utils.storage_utils import get_storage_service
from Utils.util import extract_attachments
from notification.socket import manager
import json

router = APIRouter(prefix="/employee-data-inputs", tags=["Employee Data Inputs"])

@router.post(
    "/",
    response_model=schemas.EmployeeDataInput,
    status_code=status.HTTP_201_CREATED
)
async def create_input(
    employee_id: str = Form(...),
    organization_id: str = Form(...),
    data_type: str = Form(...),
    request_type: str = Form(...),
    data: str = Form(...),                    # JSON string
    files: List[UploadFile] = File(None),       # optional attachments
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage_service),
    # current_user=Depends(deps.get_current_active_user),
):
    # obj_in = schemas.EmployeeDataInputCreate(
    #     employee_id=employee_id,
    #     data_type=data_type,
    #     request_type=request_type,
    #     data=schemas.parse_raw_as(schemas.Any, data)  # parse JSON
    # )
    # return employee_data_input.create_data_input(db=db, organization_id=organization_id, obj_in=obj_in, files=files, storage=storage)

    # parse the incoming JSON string into a native Python object
    try:
        data_dict = json.loads(data)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`data` must be a valid JSON string"
        )
    print("\n\ndata_dict", data_dict)
    print("\n\nfiles", files)
    obj_in = schemas.EmployeeDataInputCreate(
        employee_id=employee_id,
        organization_id=UUID(organization_id),
        data_type=data_type,
        request_type=request_type,
        data=data_dict
    )

    return await employee_data_input.create_or_update_data_input(
         db=db,
         organization_id=organization_id,
         obj_in=obj_in,
         files=files,
         storage=storage
     )


# @router.post(
#     "/",
#     response_model=schemas.EmployeeDataInput,
#     status_code=status.HTTP_201_CREATED,
# )
# async def create_input(
#     *,
#     obj_in: schemas.EmployeeDataInputCreate = Body(...),
#     files: List[UploadFile] = File([]),
#     db: Session = Depends(get_db),
#     storage=Depends(get_storage_service),
# ):
#     # obj_in now has all five required fields
#     return employee_data_input.create_data_input(
#         db=db,
#         organization_id=str(obj_in.organization_id),
#         obj_in=obj_in,
#         files=files,
#         storage=storage
#     )




@router.get(
    "/",
    response_model=List[schemas.EmployeeDataInput]
)
def list_data_inputs(
    employee_id: UUID = Query(..., description="Filter by employee_id"),
    db: Session = Depends(get_db),
):
    # Return all change‐requests for that employee
    return employee_data_input.get_data_inputs_by_employee_order_by_date(db, employee_id)
    # return employee_data_input.get_data_inputs_by_employee(db, employee_id)


@router.get(
    "/org/",
    response_model=List[schemas.EmployeeDataInputRead],
    summary="List all pending inputs for this organization (HR only)"
)
async def list_data_inputs(
    organization_id: UUID = Query(..., description="Your org UUID"),
    current_user  = Depends(get_current_user),   
    db: Session = Depends(get_db),

):
   # 1) Authenticate & HR-permission
    # 1) HR permission check
   
    user = current_user["user"]
    print("getUser::  ", user)
    try:
        if user.organization_id != organization_id:
            raise HTTPException(403, "Not your organization")
        
        ensure_hr_dashboard_ws(user)
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # 2) Tenant check
    if user.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your organization")
    
    # 3) Fetch inputs + employee in one go
    rows = (
        db.query(EmployeeDataInput)
            .options(joinedload(EmployeeDataInput.employee))
            .join(Employee, Employee.id == EmployeeDataInput.employee_id)
            .filter(EmployeeDataInput.organization_id == organization_id)
            .all()
    )

    # 4) Batch‐fetch related Users + roles
    emails = {row.employee.email for row in rows}
    users = (
        db.query(User)
            .options(joinedload(User.role))
            .filter(
                and_(
                    User.organization_id == organization_id,
                    User.email.in_(list(emails))
                )
            )
            .all()
    )
    user_map = {u.email: u for u in users}

    # 5) Build and broadcast payload
    payload = []
    for row in rows:
        print("employeeDataInput rowID: ", row.id)
        print("row.data: ", row.data)
        emp = row.employee
        full_name = " ".join(filter(None, [emp.first_name, emp.middle_name, emp.last_name]))
        user_rec  = user_map.get(emp.email)
        role_name = user_rec.role.name if user_rec and user_rec.role else "N/A"
        attachments = extract_attachments(row.data or {})

        payload.append({
            "id": str(row.id),
            "Account Name": full_name,
            "Role":         role_name,
            "Data": row.data,
            "Issues":       "Request Approval",
            "Attachments":  attachments,
            "Actions":      "Pending"
        })

        # payload.append({
        # "id":           str(row.id),
        # "account_name": full_name,
        # "role":         role_name,
        # "data":         row.data,
        # "issues":       "Request Approval",
        # "attachments":  attachments,
        # "actions":      "Pending",
        # })
    # return payload
    return JSONResponse(content=payload)



@router.get(
    "/{id}",
    response_model=schemas.EmployeeDataInput
)
def read_input(
    id: str,
    db: Session = Depends(get_db),
):
    db_obj = employee_data_input.get_data_input(db, id)
    print("db_obj", db_obj)
    # Check if the object exists or is None
    # If it doesn't exist, raise an HTTPException with a 404 status code
    # if db_obj is None: return {}
    if not db_obj:
        # ⚠️ must *raise* the exception, not return it
        raise HTTPException(status_code=404, detail=" Data input Not found")
    return db_obj


# @router.get(
#     "/",
#     response_model=List[schemas.EmployeeDataInput]
# )
# def read_inputs(
#     skip: int = 0,
#     limit: int = 100,
#     db: Session = Depends(get_db),
#     # current_user=Depends(deps.get_current_active_user),
# ):
#     return employee_data_input.get_data_inputs(db, skip=skip, limit=limit)


@router.patch(
    "/{id}",
    response_model=schemas.EmployeeDataInput
)
def update_input(
    id: str,
    obj_in: schemas.EmployeeDataInputUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    # current_user=Depends(deps.get_current_active_admin),
):
    
    db_obj =  employee_data_input.update_data_input(db=db, id=id, obj_in=obj_in)

    if db_obj.status in (RequestStatus.Approved, RequestStatus.Rejected):
        # Build the payload exactly as your Staff.js handler expects
        message = {
            "type": "change_request",
            "payload": {
                "request_id": str(db_obj.id),
                "status":     db_obj.status.value if hasattr(db_obj.status, 'value') else db_obj.status,
                "comments":   db_obj.comments or "",
                "data_type":  db_obj.data_type,
            }
        }

        # Schedule an async push; this won’t block the HTTP response
        background_tasks.add_task(
            manager.send_personal_message,
            str(db_obj.organization_id),
            str(db_obj.employee_id),
            json.dumps(message),
        )

        # 3️⃣ Then immediately push a fresh “update” snapshot
        full = get_employee_full_record(db, str(db_obj.employee_id))
        update_msg = {"type": "update", "payload": full}
        background_tasks.add_task(
            manager.send_personal_message,
            str(db_obj.organization_id),
            str(db_obj.employee_id),
            json.dumps(update_msg, default=lambda o: str(o)),
        )


    return db_obj
    # return employee_data_input.update_data_input(db=db, id=id, obj_in=obj_in)

@router.delete(
    "/{id}",
    response_model=schemas.EmployeeDataInput
)
def delete_input(
    id: str,
    db: Session = Depends(get_db),
    # current_user=Depends(deps.get_current_active_admin),
):
    return employee_data_input.delete_data_input(db, id)
