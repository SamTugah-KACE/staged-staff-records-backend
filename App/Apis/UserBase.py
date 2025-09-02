from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Body, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from database.db_session import SessionLocal, get_db
from Models.models import (
    Employee,
    AcademicQualification,
    ProfessionalQualification,
    EmploymentHistory,
    EmergencyContact,
    NextOfKin,
    SalaryPayment,
    EmployeePaymentDetail,
    PromotionRequest,
    EmployeeDataInput,
    Department,
    User as UserModel,
)
from Models.Tenants.organization import Organization, Branch 
from Models.Tenants.role import Role
from Models.dynamic_models import EmployeeDynamicData
from Schemas.schemas import EmployeeUserUpdateResponse  # Pydantic schema for User (includes org ID)
from Crud.auth import get_current_user
from .summary import push_summary_update



MODEL_REGISTRY: Dict[str, Type[DeclarativeMeta]] = {
    "employees": Employee,
    "academic_qualifications": AcademicQualification,
    "professional_qualifications": ProfessionalQualification,
    "employment_history": EmploymentHistory,
    "emergency_contacts": EmergencyContact,
    "next_of_kin": NextOfKin,
    "salary_payments": SalaryPayment,
    "employee_payment_details": EmployeePaymentDetail,
    "promotion_requests": PromotionRequest,
    "employee_data_inputs": EmployeeDataInput,
    "departments": Department,
    "branches": Branch,
    "employee_dynamic_data": EmployeeDynamicData,
}










router = APIRouter(prefix="/api/records", tags=["records"])

# @router.patch(
#     "/{model_name}/{record_id}",
#     status_code=status.HTTP_200_OK,
#     response_model=Dict[str, Any],
# )
# def patch_generic_record(
#     model_name: str,
#     record_id: UUID,
#     payload: Dict[str, Any] = Body(..., example={"last_name": "Smith", "custom_data": {"key": "val"}}),
#     db: Session = Depends(get_db),
#     current_user: UserRead = Depends(get_current_user),
# ):
#     """
#     Generic PATCH endpoint for any one-row update. The payload can contain
#     any fields that exist on the target model (except forbidden ones).
#     """
#     # 1) Ensure model_name is valid
#     Model = MODEL_REGISTRY.get(model_name)
#     if not Model:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Model '{model_name}' is not recognized for updates.",
#         )

#     # 2) Fetch the record, enforcing org‐scope
#     query = db.query(Model)
#     # For models with an `organization_id` column:
#     if hasattr(Model, "organization_id"):
#         instance = query.filter(
#             Model.id == record_id,
#             Model.organization_id == current_user.organization_id,
#         ).first()
#     else:
#         # some models (e.g. SalaryPayment) relate to Employee → fetch through employee’s org
#         instance = (
#             query.join(Employee, Model.employee_id == Employee.id)
#             .filter(
#                 Model.id == record_id,
#                 Employee.organization_id == current_user.organization_id,
#             )
#             .first()
#         )

#     if not instance:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Record not found or you do not have permission.",
#         )

#     # 3) Determine which fields are allowed to update
#     #    We disallow updating 'id', 'organization_id', any foreign keys that should not change, etc.
#     forbidden_fields = {"id", "organization_id", "created_at", "updated_at"}
#     # Also disallow primary‐key, relationships, etc. (we’ll check attribute existence in Model.__table__.columns)
#     columns = {col.name for col in Model.__table__.columns}

#     # 4) Loop through payload keys
#     for key, value in payload.items():
#         if key in forbidden_fields:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Field '{key}' cannot be updated directly.",
#             )
#         if key not in columns:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Field '{key}' is not a valid column on '{model_name}'.",
#             )
#         # 5) Optionally: add type coercion or extra validation here
#         setattr(instance, key, value)

#     # 6) Commit & return the updated row as a dict
#     db.add(instance)
#     db.commit()
#     db.refresh(instance)

#     # Convert to plain dict (excluding internal attrs)
#     result = {col: getattr(instance, col) for col in columns}
#     return result




@router.patch(
    "/{employee_id}",
    status_code=status.HTTP_200_OK,
    response_model=EmployeeUserUpdateResponse,
)
def update_employee_and_user(
    employee_id: UUID,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Optional[str]] = Body(
        ...,
        example={
            "department": "Sales",
            "branch": "Accra Main",
            "role_id": "083d84cf-11b8-4219-a3e1-23d616503516"
        },
    ),
    
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update an Employee's department/branch and the corresponding User's role,
    all within the same organization. Any of: "department", "branch", "role_id" may be provided.

    We enforce:
      - Employee.organization_id == current_user["user"].organization_id
      - New Department.name and Branch.name must belong to same org
      - New Role.id must belong to same org
      - The User we update is located by matching Employee.email under the same org.
    """

    # 1) Extract the logged-in user's organization_id
    user_obj = current_user["user"]            # <UserModel ORM instance>
    org_id   = user_obj.organization_id        # <UUID of org>

    # 2) Fetch the Employee row, enforcing multi-tenant isolation
    employee = (
        db.query(Employee)
        .filter(
            Employee.id == employee_id,
            Employee.organization_id == org_id,
        )
        .first()
    )
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found or you do not have permission."
        )

    # 3) If "branch" is provided, look it up under the same org
    branch_obj = None
    if payload.get("branch") is not None:
        branch_name = payload["branch"].strip()
        if not branch_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Branch name cannot be empty."
            )
        branch_obj = (
            db.query(Branch)
            .filter(
                Branch.name == branch_name,
                Branch.organization_id == org_id,
            )
            .first()
        )
        if not branch_obj:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Branch '{branch_name}' not found in your organization."
            )

    # 4) If "department" is provided, look it up under the same org (and, if branch_obj exists, limit to that branch)
    department_obj = None
    if payload.get("department") is not None:
        dept_name = payload["department"].strip()
        if not dept_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department name cannot be empty."
            )
        query_dept = db.query(Department).filter(
            Department.name == dept_name,
            Department.organization_id == org_id,
        )
        if branch_obj:
            query_dept = query_dept.filter(Department.branch_id == branch_obj.id)

        department_obj = query_dept.first()
        if not department_obj:
            msg = f"Department '{dept_name}' not found in your organization"
            if branch_obj:
                msg += f" (or it does not belong to branch '{branch_obj.name}')."
            else:
                msg += "."
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        # 4a) Assign new department_id on Employee
        employee.department_id = department_obj.id

    # 5) Find the associated User record by `employee.email` under the same org
    #    We assume: User.email == Employee.email, and User.organization_id == org_id
    linked_user = (
        db.query(UserModel)
        .filter(
            UserModel.email == employee.email,
            UserModel.organization_id == org_id,
        )
        .first()
    )
    if not linked_user:
        # In a correct setup, every Employee should have a User. If not, it's an error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Linked User record not found for this Employee."
        )

    # 6) If "role_id" is provided, ensure that Role belongs to the same org, then assign
    if payload.get("role_id") is not None:
        try:
            new_role_uuid = UUID(payload["role_id"])
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role_id format."
            )

        role_obj = (
            db.query(Role)
            .filter(
                Role.id == new_role_uuid,
                Role.organization_id == org_id,
            )
            .first()
        )
        if not role_obj:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role not found or does not belong to your organization."
            )

        linked_user.role_id = role_obj.id

    # 7) Commit all changes in one go
    db.add(employee)
    db.add(linked_user)
    db.commit()
    db.refresh(employee)
    db.refresh(linked_user)

    # 8) Build the response in the shape the front end expects
    #    We return exactly: employee_id, staffId, name, department, branch, role.
    updated_dept: Optional[dict] = None
    updated_branch: Optional[dict] = None

    if employee.department:
        updated_dept = {
            "id":        str(employee.department.id),
            "name":      employee.department.name,
            "branch_id": str(employee.department.branch_id) if employee.department.branch_id else None,
        }
        if employee.department.branch_id:
            b = employee.department.branch
            updated_branch = {
                "id":       str(b.id),
                "name":     b.name,
                "location": b.location,
            }

    updated_role = {
        "id":   str(linked_user.role.id),
        "name": linked_user.role.name,
    }

    response_payload = EmployeeUserUpdateResponse(
        employee_id = str(employee.id),
        staffId      = employee.staff_id if employee.staff_id else None,
        name         = f"{employee.first_name}"
                       f"{(' ' + employee.middle_name) if employee.middle_name else ''}"
                       f" {employee.last_name}",
        department   = updated_dept,
        branch       = updated_branch if updated_branch else None,
        role         = updated_role,
    )

    background_tasks.add_task(push_summary_update, db, str(org_id))

    return response_payload




@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_200_OK,
    response_model=dict,
)
def delete_or_archive_employee(
    employee_id: UUID,
    background_tasks: BackgroundTasks,
    deleteType: str = Depends(lambda deleteType: deleteType),  # e.g. "soft" or "hard"
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    If deleteType == "soft", mark both Employee.is_active=False and User.is_active=False.
    If deleteType == "hard", permanently delete Employee and User.
    """
    user_obj = current_user["user"]
    org_id   = user_obj.organization_id

    # 1) Fetch the Employee under the same org:
    employee = (
        db.query(Employee)
        .filter(
            Employee.id == employee_id,
            Employee.organization_id == org_id,
        )
        .first()
    )
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found or you do not have permission."
        )

    # 2) Fetch linked User
    linked_user = (
        db.query(UserModel)
        .filter(
            UserModel.email == employee.email,
            UserModel.organization_id == org_id,
        )
        .first()
    )

    if deleteType == "soft":
        # Soft delete: set both flags to False
        employee.is_active = False
        if linked_user:
            linked_user.is_active = False

        db.add(employee)
        if linked_user:
            db.add(linked_user)
        db.commit()

        return {
            "employee_id": str(employee_id),
            "soft_deleted": True
        }

    # Otherwise, deleteType == "hard"
    if linked_user:
        db.delete(linked_user)
    db.delete(employee)
    db.commit()
    background_tasks.add_task(push_summary_update, db, str(org_id))
    return {
        "employee_id": str(employee_id),
        "deleted": True
    }