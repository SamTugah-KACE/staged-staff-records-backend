import json
from fastapi import APIRouter, Depends, File, status, HTTPException, UploadFile, BackgroundTasks, Query, Form
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Union
from uuid import UUID
from Apis.summary import _build_summary_payload, push_summary_update
from Utils.util import get_organization_acronym
from Service.email_service import EmailService, get_email_template
from Utils.security import Security
from database.db_session import get_db, get_async_db  # Dependency injection
from Models.Tenants.organization import Organization
from Models.Tenants.role import Role
from Models.models import (
    User,
    Employee,
    AcademicQualification,
    EmploymentHistory,
    EmergencyContact,
    NextOfKin,
    FileStorage,
    AuditLog
)
from Schemas.schemas import (
    OrganizationCreateSchema, OrganizationSchema,
    DepartmentCreate, DepartmentOut, DepartmentUpdate,
    RoleCreateSchema, RoleSchema, StaffOption,
    UserCreateSchema, UserSchema,
    EmployeeCreateSchema, EmployeeSchema,
    AcademicQualificationCreateSchema, AcademicQualificationSchema,
    EmploymentHistoryCreateSchema,  EmploymentHistorySchema,
    NextOfKinCreateSchema,  NextOfKinSchema,
    FileStorageSchema, 
)
from Crud.auth import get_current_user, get_db, require_permissions  # RBAC dependency from earlier
from Crud.role_crud import (create_role, get_role, get_role_by_id_and_org_id, get_roles_by_org, 
                            update_role, delete_role, get_role_permissions, get_roles_by_permission, 
                            get_role_by_name, get_role_by_name_and_org, get_role_by_name_and_org_id, 
                                                        
                            )
from Crud.base import CRUDBase
from Crud.department import *
from Crud.async_base import CRUDBase as AsyncCRUDBase
from Utils.config import DevelopmentConfig




settings = DevelopmentConfig()



# Initialize the global Security instance.
# In a multi-tenant system sharing one schema, a common secret key is often used.
global_security = Security(secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM, token_expire_minutes=60)

router = APIRouter()

# CRUDBase instances
organization_crud = CRUDBase(Organization, AuditLog)
role_crud = CRUDBase(Role, AuditLog)
user_crud = CRUDBase(User, AuditLog)
employee_crud = CRUDBase(Employee, AuditLog)
academic_crud = CRUDBase(AcademicQualification, AuditLog)
employment_history_crud = CRUDBase(EmploymentHistory, AuditLog)
emergency_contact_crud = CRUDBase(EmergencyContact, AuditLog)
next_of_kin_crud = CRUDBase(NextOfKin, AuditLog)
file_storage_crud = CRUDBase(FileStorage, AuditLog)


@router.get(
    "/enlist/staff",
    response_model=List[StaffOption],
    summary="List all staff in your org (excluding yourself)",
)
def enlist_staff(
    organization_id: UUID = Query(..., description="Your tenant’s org ID"),
    skip: int = Query(0, ge=0, description="How many records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    sort: str = Query("asc", regex="^(asc|desc)$", description="Sort by first name"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Returns a paginated list of employees in the given organization,
    excluding the employee record of the requesting user.
    """
    user: User = current_user["user"]

    # 1) Tenant isolation
    if user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not permitted for this organization."
        )

    # 2) Base query, exclude yourself by email
    query = (
        db.query(Employee)
          .filter(Employee.organization_id == organization_id)
          .filter(Employee.email != user.email)
    )

    # 3) Sorting
    if sort == "asc":
        query = query.order_by(Employee.first_name.asc())
    else:
        query = query.order_by(Employee.first_name.desc())

    # 4) Pagination
    staff_list = query.offset(skip).limit(limit).all()

    return staff_list



#Department endpoints
@router.post("/organizations/{org_id}/departments", response_model=DepartmentOut,  tags=["Organizational Departments"])
async def create_department_endpoint(org_id: uuid.UUID, dept_in: DepartmentCreate, db: Session = Depends(get_db)):
    """
    Create a new department for the given organization.
    """
    # org = db.query(Organization).filter(Organization.id == org_id).first()
    # if not org:
    #     raise HTTPException(status_code=404, detail="Organization not found")
    department = create_department(org_id, db, dept_in)
    asyncio.create_task(push_summary_update(db, str(org_id)))
    return department



@router.get("/organizations/{org_id}/departments", response_model=list[DepartmentOut],  tags=["Organizational Departments"])
def list_departments_endpoint(org_id: uuid.UUID, db: Session = Depends(get_db), skip: int = 0,
    limit: int = 10):
    """
    List all departments for a given organization.
    """
    departments = get_departments(db, organization_id=org_id, skip=skip, limit=limit)
    return departments

@router.get("/organizations/{org_id}/departments/{dept_id}", response_model=DepartmentOut,  tags=["Organizational Departments"])
def get_department_endpoint(org_id: uuid.UUID, dept_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Retrieve a single department by its ID for the given organization.
    """
    department = get_department(db, dept_id)
    if not department or department.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Department not found")
    return department

@router.patch("/organizations/{org_id}/departments/{dept_id}", response_model=DepartmentOut,  tags=["Organizational Departments"])
async def update_department_endpoint(org_id: uuid.UUID, dept_id: uuid.UUID, dept_in: DepartmentUpdate, db: Session = Depends(get_db)):
    """
    Update an existing department for the given organization.
    """
    department = get_department(db, dept_id)
    if not department or department.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Department not found")
    updated_department = update_department(db, department, dept_in)
    asyncio.create_task(push_summary_update(db, str(org_id)))
    return updated_department

@router.delete("/organizations/{org_id}/departments/{dept_id}",  tags=["Organizational Departments"])
async def delete_department_endpoint(org_id: uuid.UUID, dept_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Delete a department from the given organization.
    """
    department = get_department(db, dept_id)
    if not department or department.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Department not found")
    delete_department(db, department)

    asyncio.create_task(push_summary_update(db, str(org_id)))
    # build fresh summary  and broadcast to the request organization
    # schema_obj = await _build_summary_payload(db, org_id)
    # payload = jsonable_encoder(schema_obj)  # <-- turns Pydantic schema into plain dict
    # message = json.dumps({"type": "update", "payload": payload})

    # # Fire-and-forget so HTTP response isn't delayed
    # asyncio.create_task(manager.broadcast(str(org_id), message))
    return {"detail": "Department deleted successfully"}











### User Endpoints ###
@router.post("/roles", tags=["Roles"], response_model=RoleCreateSchema)
async def create_roles(
    obj_in: RoleCreateSchema,
    db: Session = Depends(get_db),
    created_by: Optional[UUID] = None,
):
    try:
        result =  role_crud.create(db=db, obj_in=obj_in,user_id=created_by )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/role", tags=["Roles"], response_model=RoleCreateSchema)
async def create(
    obj_in: RoleCreateSchema,
    db: Session = Depends(get_db),
    created_by: Optional[UUID] = None,
):
    try:
        result =  create_role(db=db, obj_in=obj_in,user_id=created_by )
        
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fetch", tags=["Roles"], response_model=Union[List[RoleSchema], dict], summary="Fetch roles (requires organization_id filter).")
async def list_roles(
    # Require at least one organization_id; if not provided, we return an empty list.
    # organization_id: Optional[List[UUID]] = Query(
    #     None, 
    #     description="Filter roles by one or more organization IDs."
    # ),
    organization_id: Optional[str] = Query(
        None, description="Either a UUID (or comma-separated UUIDs) for filtering or the keyword 'all'."
    ),
    skip: int = 0,
    limit: int = 10,
    # Optional grouping parameter – for example, grouping by organization_id.
    group_by: Optional[str] = Query(
        None, description="Optional grouping field (e.g. 'organization_id')."
    ),
    db: Session = Depends(get_db),
):
    # Enforce that roles cannot be fetched unless an organization filter is provided.
    if not organization_id:
        return []

    # Build filters dynamically.
    filters = {}
     # Check if the user wants all roles across organizations.
    if organization_id.lower() == "all":
        filters = None  # No organization filter applied
    else:
        # If multiple UUIDs are supplied as a comma-separated string
        org_ids = [UUID(id.strip()) for id in organization_id.split(",")]
        if len(org_ids) == 1:
            filters = {"organization_id": {"eq": org_ids[0]}}
        else:
            filters = {"organization_id": {"in": org_ids}}

    result = role_crud.get_multi(db, filters=filters, skip=skip, limit=limit, group_by=group_by)
    # Convert the ORM objects to Pydantic models before returning.
    if isinstance(result, dict):
        flat_roles = [RoleSchema.from_orm(role) for role in result.get("flat", [])]
        grouped_roles = {
            key: [RoleSchema.from_orm(role) for role in roles]
            for key, roles in result.get("grouped", {}).items()
        }
        return {"flat": flat_roles, "grouped": grouped_roles}
    else:
        return [RoleSchema.from_orm(role) for role in result]



@router.get("/roles/{role_id}", tags=["Roles"], response_model=RoleSchema)
def get_role_by_id(
    role_id: UUID,
    organization_id: UUID = Query(..., description="Organization ID for multi-tenancy"),
    db: Session = Depends(get_db)
):
    """
    Retrieves a role record by its ID and organization ID.
    """
    # reference = {"id": role_id, "organization_id": organization_id}
    try:
        # result = role_crud.get(db, reference)
        result = get_role_by_id_and_org_id(db, role_id, organization_id)
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles/name/{role_name}", tags=["Roles"], response_model=RoleSchema)
def get_role_by_name(
    role_name: str,
    organization_id: UUID = Query(..., description="Organization ID for multi-tenancy"),
    db: Session = Depends(get_db)
):
    """
    Retrieves a role record by its name and organization ID.
    """
    # reference = {"name": role_name, "organization_id": organization_id}
    try:
        result = get_role_by_name_and_org_id(db, role_name, organization_id)
        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))










@router.get("/users/{user_id}", response_model=Dict, tags=["User Management"])
def get_user(
    user_id: UUID,
    organization_id: UUID = Query(..., description="Organization ID for multi-tenancy"),
    include_files: bool = Query(False, description="Set to true to include file content for image_path, etc."),
    max_file_size: int = Query(2 * 1024 * 1024, description="Maximum file size (in bytes) to download (default: 2 MB)"),
    db: Session = Depends(get_db)
):
    """
    Retrieves a user record by its ID and organization ID.

    - **user_id**: The unique identifier for the user.
    - **organization_id**: The organization the user belongs to.
    - **include_files**: If true, and if the user has file URL fields (like image_path),
      their content will be downloaded (provided the file is below max_file_size) and included.
    - **max_file_size**: The maximum size (in bytes) allowed for downloading file content.
      A value of 2 MB is recommended for profile images.
    """
    reference = {"id": user_id, "organization_id": organization_id}
    try:
        result = user_crud.get(db, reference, include_files=include_files, max_file_size=max_file_size)
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


# ### Employee Endpoints ###
@router.post("/staff", tags=["Employee Management"], response_model=EmployeeCreateSchema)
async def create_employee(
    emp_data: EmployeeCreateSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    role_id: Optional[UUID] = None,
    created_by: Optional[UUID] = None,
    file: Optional[List[UploadFile]] = File(None), 
):
    try:
        # Generate a temporary plain-text password for the new user.
        plain_password = global_security.generate_random_string(6)
        # Attach the generated password as a transient attribute.
        # (Pydantic models allow you to set arbitrary attributes.)
        emp_data._plain_password = plain_password
        emp_data._role_id = role_id  # Will be used by the event listener

        # Call the CRUD function to create the employee.
        result = await employee_crud.create_employee(db=db, obj_in=emp_data, role_id=role_id, user_id=created_by, file=file)

        # Retrieve the organization details to include in the email template.
        org = db.query(Organization).filter(Organization.id == emp_data.organization_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")
        
        # Prepare email details using template.
        template_data = {
            "organization_name": org.name,
            "employee_name": f"{emp_data.title or ''} {emp_data.first_name} {emp_data.last_name}".strip(),
            "user_avatar": "👤",  # Default avatar emoji
            "username": result.email,
            "password": plain_password,
            "login_url": org.access_url + "/signin"
        }

        # Schedule sending the email in the background.
        email_service = EmailService()  # instantiate your email service as needed
        background_tasks.add_task(
            email_service.send_email,
            background_tasks,
            recipients=[result.email],
            subject=f"Welcome to {org.name} - Your Account is Ready",
            template_name="organization_created.html",
            template_data=template_data
        )

        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/staff/{staff_id}", response_model=Dict, tags=["Employee Management"])
def get_user(
    staff_id: UUID,
    organization_id: UUID = Query(..., description="Organization ID for multi-tenancy"),
    include_files: bool = Query(False, description="Set to true to include file content for profile_image_path, etc."),
    max_file_size: int = Query(2 * 1024 * 1024, description="Maximum file size (in bytes) to download (default: 2 MB)"),
    db: Session = Depends(get_db)
):
    """
    Retrieves a staff record by its ID and organization ID.

    - **staff_id**: The unique identifier for the staff.
    - **organization_id**: The organization the user belongs to.
    - **include_files**: If true, and if the user has file URL fields (like profile_image_path),
      their content will be downloaded (provided the file is below max_file_size) and included.
    - **max_file_size**: The maximum size (in bytes) allowed for downloading file content.
      A value of 2 MB is recommended for profile images.
    """
    reference = {"id": staff_id, "organization_id": organization_id}
    try:
        result = employee_crud.get(db, reference, include_files=include_files, max_file_size=max_file_size)
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/staff", tags=["Employee Management"], response_model=Union[List[EmployeeSchema], dict], summary="Fetch employees (requires organization_id filter).")
async def list_staff(
    # Require at least one organization_id; if not provided, we return an empty list.
    # organization_id: Optional[List[UUID]] = Query(
    #     None, 
    #     description="Filter roles by one or more organization IDs."
    # ),
    organization_id: Optional[str] = Query(
        None, description="Either a UUID (or comma-separated UUIDs) for filtering or the keyword 'all'."
    ),
    skip: int = 0,
    limit: int = 10,
    # Optional grouping parameter – for example, grouping by organization_id.
    group_by: Optional[str] = Query(
        None, description="Optional grouping field (e.g. 'organization_id')."
    ),
    db: Session = Depends(get_db),
):
    # Enforce that roles cannot be fetched unless an organization filter is provided.
    if not organization_id:
        return []

    # Build filters dynamically.
    filters = {}
     # Check if the user wants all roles across organizations.
    if organization_id.lower() == "all":
        filters = None  # No organization filter applied
    else:
        # If multiple UUIDs are supplied as a comma-separated string
        org_ids = [UUID(id.strip()) for id in organization_id.split(",")]
        if len(org_ids) == 1:
            filters = {"organization_id": {"eq": org_ids[0]}}
        else:
            filters = {"organization_id": {"in": org_ids}}

    result = employee_crud.get_multi(db, filters=filters, skip=skip, limit=limit, group_by=group_by)
    # Convert the ORM objects to Pydantic models before returning.
    if isinstance(result, dict):
        flat_employees = [EmployeeSchema.from_orm(employee) for employee in result.get("flat", [])]
        grouped_employees = {
            key: [EmployeeSchema.from_orm(employee) for employee in employees]
            for key, employees in result.get("grouped", {}).items()
        }
        return {"flat": flat_employees, "grouped": grouped_employees}
    else:
        return [EmployeeSchema.from_orm(employee) for employee in result]


@router.patch("/staff/{staff_id}", tags=["Employee Management"], response_model=EmployeeSchema)
async def update_employee(
    staff_id: UUID,
    # organization_id: UUID = Form(..., description="Organization ID for multi-tenancy"),
    emp_data: EmployeeSchema = Form(),
    db: Session = Depends(get_db),
):
    try:
        result = await employee_crud.update(db=db, reference= {"id": staff_id}, obj_in=emp_data)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @router.delete("/rm/{emp_id}", tags=["Employees"])
# async def delete_employee(
#     emp_id: UUID,
#     db: AsyncSession = Depends(get_async_db),
#     soft_delete: Optional[bool] = Query(False),
#     force_delete: Optional[bool] = Query(False),
# ):
#     try:
#         result = await employee_crud.delete(db, {"id": emp_id}, soft_delete=soft_delete, force_delete=force_delete)
#         return {"message": "Employee deleted successfully"}
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))






# @router.get("/{user_id}", tags=["Users"], response_model=UserSchema)
# async def get_user(
#     user_id: UUID,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     try:
#         result = await user_crud.get(db, {"id": user_id})
#         return result
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.put("/update/{user_id}", tags=["Users"], response_model=UserSchema)
# async def update_user(
#     user_id: UUID,
#     user_data: UserSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     try:
#         result = await user_crud.update(db, {"id": user_id}, obj_in=user_data)
#         return result
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.delete("/rm/{user_id}", tags=["Users"])
# async def delete_user(
#     user_id: UUID,
#     db: AsyncSession = Depends(get_async_db),
#     soft_delete: Optional[bool] = Query(False),
#     force_delete: Optional[bool] = Query(False),
# ):
#     try:
#         result = await user_crud.delete(db, {"id": user_id}, soft_delete=soft_delete, force_delete=force_delete)
#         return {"message": "User deleted successfully"}
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))





# academic_crud = CRUDBase(AcademicQualification)

# @router.post("/add/", response_model=AcademicQualificationCreateSchema, tags=["AcademicQualification"])
# async def create_academic_qualification(
#     academic_data: AcademicQualificationCreateSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await academic_crud.create(db, academic_data)

# # @router.get("/", response_model=List[AcademicQualificationReadSchema], tags=["AcademicQualification"])
# # async def list_academic_qualifications(
# #     skip: int = 0,
# #     limit: int = 10,
# #     filters: dict = Query(None),
# #     db: AsyncSession = Depends(get_async_db),
# # ):
# #     return await academic_crud.get_multi(db, filters, skip, limit)

# @router.get("/get/{id}", response_model=AcademicQualificationSchema, tags=["AcademicQualification"])
# async def get_academic_qualification(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await academic_crud.get(db, {"id": id})

# @router.put("/update/{id}", response_model=AcademicQualificationSchema, tags=["AcademicQualification"])
# async def update_academic_qualification(
#     id: str,
#     academic_data: AcademicQualificationSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await academic_crud.update(db, {"id": id}, academic_data)

# @router.delete("/rm/{id}", tags=["AcademicQualification"])
# async def delete_academic_qualification(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await academic_crud.delete(db, {"id": id})


# employment_crud = CRUDBase(EmploymentHistory)

# @router.post("/add/", response_model=EmploymentHistoryCreateSchema, tags=["EmploymentHistory"])
# async def create_employment_history(
#     employment_data: EmploymentHistoryCreateSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await employment_crud.create(db, employment_data)

# # @router.get("/", response_model=List[EmploymentHistoryReadSchema], tags=["EmploymentHistory"])
# # async def list_employment_histories(
# #     skip: int = 0,
# #     limit: int = 10,
# #     filters: dict = Query(None),
# #     db: AsyncSession = Depends(get_async_db),
# # ):
# #     return await employment_crud.get_multi(db, filters, skip, limit)

# @router.get("/get/{id}", response_model=EmploymentHistorySchema, tags=["EmploymentHistory"])
# async def get_employment_history(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await employment_crud.get(db, {"id": id})

# @router.put("/update/{id}", response_model=EmploymentHistorySchema, tags=["EmploymentHistory"])
# async def update_employment_history(
#     id: str,
#     employment_data: EmploymentHistorySchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await employment_crud.update(db, {"id": id}, employment_data)

# @router.delete("/rm/{id}", tags=["EmploymentHistory"])
# async def delete_employment_history(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await employment_crud.delete(db, {"id": id})

# emergency_contact_crud = CRUDBase(EmergencyContact)

# @router.post("/add/", response_model=EmergencyContactSchema, tags=["EmergencyContact"])
# async def create_emergency_contact(
#     contact_data: EmergencyContactCreateSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await emergency_contact_crud.create(db, contact_data)

# # @router.get("/", response_model=List[EmergencyContactReadSchema], tags=["EmergencyContact"])
# # async def list_emergency_contacts(
# #     skip: int = 0,
# #     limit: int = 10,
# #     filters: dict = Query(None),
# #     db: AsyncSession = Depends(get_async_db),
# # ):
# #     return await emergency_contact_crud.get_multi(db, filters, skip, limit)

# @router.get("/get/{id}", response_model=EmergencyContactReadSchema, tags=["EmergencyContact"])
# async def get_emergency_contact(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await emergency_contact_crud.get(db, {"id": id})

# @router.put("/update/{id}", response_model=EmergencyContactReadSchema, tags=["EmergencyContact"])
# async def update_emergency_contact(
#     id: str,
#     contact_data: EmergencyContactUpdateSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await emergency_contact_crud.update(db, {"id": id}, contact_data)

# @router.delete("/rm/{id}", tags=["EmergencyContact"])
# async def delete_emergency_contact(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await emergency_contact_crud.delete(db, {"id": id})


# next_of_kin_crud = CRUDBase(NextOfKin)

# @router.post("/add/", response_model=NextOfKinReadSchema, tags=["NextOfKin"])
# async def create_next_of_kin(
#     kin_data: NextOfKinCreateSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await next_of_kin_crud.create(db, kin_data)

# # @router.get("/", response_model=List[NextOfKinReadSchema], tags=["NextOfKin"])
# # async def list_next_of_kin(
# #     skip: int = 0,
# #     limit: int = 10,
# #     filters: dict = Query(None),
# #     db: AsyncSession = Depends(get_async_db),
# # ):
# #     return await next_of_kin_crud.get_multi(db, filters, skip, limit)

# @router.get("/next/{id}", response_model=NextOfKinReadSchema, tags=["NextOfKin"])
# async def get_next_of_kin(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await next_of_kin_crud.get(db, {"id": id})

# @router.put("/update/{id}", response_model=NextOfKinReadSchema, tags=["NextOfKin"])
# async def update_next_of_kin(
#     id: str,
#     kin_data: NextOfKinUpdateSchema,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await next_of_kin_crud.update(db, {"id": id}, kin_data)

# @router.delete("/rm/{id}", tags=["NextOfKin"])
# async def delete_next_of_kin(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await next_of_kin_crud.delete(db, {"id": id})

# file_storage_crud = CRUDBase(FileStorage)

# @router.post("/add-file/", response_model=FileStorageReadSchema, tags=["FileStorage"])
# async def create_file(
#     file_data: FileStorageCreateSchema,
#     file: UploadFile,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await file_storage_crud.create(db, file_data, file=file)

# # @router.get("/", response_model=List[FileStorageReadSchema], tags=["FileStorage"])
# # async def list_files(
# #     skip: int = 0,
# #     limit: int = 10,
# #     filters: dict = Query(None),
# #     db: AsyncSession = Depends(get_async_db),
# # ):
# #     return await file_storage_crud.get_multi(db, filters, skip, limit)

# @router.get("/fetch/{id}", response_model=FileStorageReadSchema, tags=["FileStorage"])
# async def get_file(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await file_storage_crud.get(db, {"id": id})

# @router.put("/update-file/{id}", response_model=FileStorageReadSchema, tags=["FileStorage"])
# async def update_file(
#     id: str,
#     file_data: FileStorageUpdateSchema,
#     file: UploadFile,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await file_storage_crud.update(db, {"id": id}, file_data, file=file)

# @router.delete("/rm/{id}", tags=["FileStorage"])
# async def delete_file(
#     id: str,
#     db: AsyncSession = Depends(get_async_db),
# ):
#     return await file_storage_crud.delete(db, {"id": id})

