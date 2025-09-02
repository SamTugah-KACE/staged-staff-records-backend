from fastapi import HTTPException
from sqlalchemy.orm import Session
from Models.models import Department
from Models.Tenants.organization import Branch, Organization
from Schemas.schemas import BranchCreate, BranchUpdate
import uuid

def create_branch(db: Session, branch_in: BranchCreate, organization_id: uuid.UUID) -> Branch:
    try:

        is_org_branched = db.query(Organization).filter(Organization.id == organization_id, Organization.nature == "Branch Managed").first()
        if not is_org_branched:
            raise HTTPException(status_code=400, detail="Organization is managed single-handedly.\nPlease Update Organization Data to allow creation of branches.")

        is_branch_exist = db.query(Branch).filter(Branch.name == branch_in.name, Organization.id == organization_id).first()
        if is_branch_exist:
            raise HTTPException(status_code=400, detail=f"{branch_in.name} already exist.")
        
        if branch_in.manager_id:
            is_hod_already_assigned = db.query(Department).filter(Department.department_head_id == branch_in.manager_id, Department.organization_id == organization_id).first()
            if is_hod_already_assigned:
                raise HTTPException(status_code=400, detail="Staff already assigned as the Head of Department.")
       
        if branch_in.manager_id:
            is_manager_already_assigned = db.query(Branch).filter(Branch.manager_id == branch_in.manager_id, Organization.id == organization_id).first()
            if is_manager_already_assigned:
                raise HTTPException(status_code=400, detail="Staff already assigned as a Manager in other Branch.")
        
        
        branch = Branch(**branch_in.dict(), organization_id=organization_id)
        db.add(branch)
        db.commit()
        db.refresh(branch)
        return branch
    except HTTPException:
        # Re-raise any HTTPExceptions you threw yourself above
        raise
    except Exception as e:
        print("\n\nerror creating branch: ",e)
        raise HTTPException(status_code=500, detail=f"error occurred while creating branch '{branch_in.name}':\n {str(e)}")
    

def get_branches(db: Session, organization_id: uuid.UUID, skip: int = 0, limit: int = 100):
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if not org:
        raise HTTPException(status_code=400, detail="Organization not found.")
    
    is_branched = org.nature.lower()
    print("is_branched:: ", is_branched)
    if "single" in is_branched :
        raise HTTPException(status_code=400, detail="Organization is a Single Managed, hence has no Branches.")

    return db.query(Branch).filter(Branch.organization_id == organization_id).offset(skip).limit(limit).all()


def get_branch(db: Session, branch_id: uuid.UUID):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=400, detail="Branch not found.")
    
    return db.query(Branch).filter(Branch.id == branch_id).first()

def update_branch(db: Session, branch: Branch, branch_in: BranchUpdate) -> Branch:
    # brach = db.query(Branch).filter(Branch.id == branch.id).first()
    # if not brach:
    #     raise HTTPException(status_code=400, detail="Branch not found.")
    update_data = branch_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(branch, key, value)
    db.commit()
    db.refresh(branch)
    return branch


def delete_branch(db: Session, branch: Branch):
    db.delete(branch)
    db.commit()
