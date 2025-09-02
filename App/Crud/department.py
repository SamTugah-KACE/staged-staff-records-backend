import asyncio
import json
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from Apis.summary import _build_summary_payload, push_summary_update
from Models.Tenants.organization import Organization, Branch
from Models.models import Department
from Schemas.schemas import DepartmentCreate, DepartmentUpdate, DepartmentOut
import uuid
from notification.socket import manager
from sqlalchemy.exc import IntegrityError

def create_department(organization_id:uuid.UUID, db: Session, dept_in: DepartmentCreate) -> Department:
    try:

        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise HTTPException(status_code=400, detail="Organization not found.")

        is_dept_exist = db.query(Department).filter(Department.name == dept_in.name.strip(), Department.organization_id == organization_id).first()
        if is_dept_exist:
            raise HTTPException(status_code=400, detail=f"{dept_in.name} already exist.")
        
        if dept_in.department_head_id:
            is_hod_already_assigned = db.query(Department).filter(Department.department_head_id == dept_in.department_head_id, Department.organization_id == organization_id).first()
            if is_hod_already_assigned:
                raise HTTPException(status_code=400, detail="Staff[HoD] already assigned to another Department.")
        
        
        
        if dept_in.branch_id:
            if org.nature != "Branch Managed":
                raise HTTPException(status_code=400, detail=f"'{org.name}' data indicates its Managed Single-handedly, therefore, there's no need to assign '{dept_in.name}' to a given Branch.")
        
            is_dept_exist_in_same_branch = db.query(Department).filter(Department.name == dept_in.name.strip(), Department.branch_id == dept_in.branch_id).first()
            if is_dept_exist_in_same_branch:
                raise HTTPException(status_code=400, detail="Department already exist within same same Branch.")
            
            # if branch_in.manager_id:
            is_manager_already_assigned = db.query(Branch).filter(Branch.manager_id == dept_in.department_head_id, Organization.id == organization_id).first()
            if is_manager_already_assigned:
                raise HTTPException(status_code=400, detail="Staff assigned as a Branch Manager.")
            

        # Create the department
        department = Department(**dept_in.dict(), organization_id=organization_id)
        db.add(department)
        db.commit()
        db.refresh(department)

        # build fresh summary  and broadcast to the request organization
        # schema_obj = await _build_summary_payload(db, organization_id)
        # payload = jsonable_encoder(schema_obj)  # <-- turns Pydantic schema into plain dict
        # message = json.dumps({"type": "update", "payload": payload})

        # # Fire-and-forget so HTTP response isn't delayed
        # asyncio.create_task(manager.broadcast(str(organization_id), message))
        # push_summary_update(db, organization_id)
        
        return department
    except IntegrityError as e:
        db.rollback()
        # inspect which constraint failed
        msg = str(e.orig).lower()
        if "uq_department_name_per_org" in msg:
            raise HTTPException(400, f"Department “{dept_in.name}” already exists.")
        if "uq_hod_per_org" in msg:
            raise HTTPException(400, "That staff[HoD] is already assigned to another Department.")
        # fallback
        raise HTTPException(400, "Could not create department.\n", msg)
    except HTTPException:
        # Re-raise any HTTPExceptions you threw yourself above
        raise
    except Exception as e:
        print("\n\nerror creating department: ",e)
        raise HTTPException(status_code=500, detail=f"error occurred while creating department '{dept_in.name}':\n {str(e)}")
    

def get_departments(db: Session, organization_id: uuid.UUID, skip: int = 0, limit: int = 100):
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if not org:
        raise HTTPException(status_code=400, detail="Organization not found.")
    
    return db.query(Department).filter(Department.organization_id == organization_id).offset(skip).limit(limit).all()


def get_department(db: Session, dept_id: uuid.UUID):
    id = db.query(Department).filter(Department.id == dept_id).first()
    if not id:
        raise HTTPException(status_code=400, detail="Department not found.")
    
    return db.query(Department).filter(Department.id == dept_id).first()

def update_department(db: Session, department: Department, dept_in: DepartmentUpdate) -> Department:
    # depart = db.query(Department).filter(Department.id == department.id).first()
    # if not depart:
    #     raise HTTPException(status_code=400, detail="Department not found.")
    update_data = dept_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(department, key, value)
    db.commit()
    db.refresh(department)
    # asyncio.create_task(push_summary_update(db, department.organization_id))
    return department

def delete_department(db: Session, department: Department):
    db.delete(department)
    db.commit()
    # push_summary_update(db, department.organization_id)
    # asyncio.create_task(push_summary_update(db, department.organization_id))
