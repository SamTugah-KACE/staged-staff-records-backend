# role_crud.py
import asyncio
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from Apis.summary import push_summary_update
from Models.Tenants.role import Role
from uuid import UUID
from sqlalchemy.exc import IntegrityError

def create_role(db: Session, obj_in, user_id: Optional[UUID] = None) -> Role:
    """
    Enhanced create method to handle insertion of selected permissions.
    The obj_in is a Pydantic model (RoleCreateSchema) that includes:
      - name
      - permissions: a list of permission strings (subset of standard_permissions)
      - organization_id
    This method creates a Role and handles nested relationships if needed.
    """
    try:
        # (Optional) Enforce uniqueness on role name within an organization.
        if db.query(Role).filter(
            Role.name == obj_in.name,
            Role.organization_id == obj_in.organization_id
        ).first():
            raise HTTPException(
                status_code=400,
                detail=f"A role with name '{obj_in.name}' already exists for this organization."
            )

        # Create the Role using the permissions list provided in the obj_in.
        role_data = obj_in.dict(exclude_unset=True)
        print("Role data:", role_data)  # Debugging line
        # Ensure the permissions are a list of strings
        new_role = Role(
            name=role_data.get("name"),
            permissions=role_data.get("permissions", []),
            organization_id=role_data.get("organization_id"),
        )
        
        db.add(new_role)
        db.commit()
        db.refresh(new_role)
        asyncio.create_task(push_summary_update(db, role_data.get("organization_id")))
        return new_role

    except IntegrityError as e:
        db.rollback()
        raise e
    except Exception as e:
        raise e
    except Exception as e:
        # db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    

def get_role(db: Session, role_id: UUID) -> Role:
    """
    Retrieve a role by its ID.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def get_roles_by_org(db: Session, organization_id: UUID, skip: int = 0, limit: int = 100) -> list:
    """
    Retrieve all roles for a given organization.
    """
    roles = db.query(Role).filter(Role.organization_id == organization_id).offset(skip).limit(limit).all()
    return roles


def update_role(db: Session, role_id: UUID, role_in) -> Role:
    """
    Update an existing role with new data.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Update the role attributes based on the incoming data
    for key, value in role_in.dict(exclude_unset=True).items():
        setattr(role, key, value)
    
    db.commit()
    db.refresh(role)
    asyncio.create_task(push_summary_update(db, str(role.organization_id)))
    return role


def delete_role(db: Session, role_id: UUID) -> None:
    """
    Delete a role by its ID.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    db.delete(role)
    db.commit()
    asyncio.create_task(push_summary_update(db, str(role.organization_id)))
    return None

def get_role_permissions(db: Session, role_id: UUID) -> list:
    """
    Retrieve all permissions associated with a specific role.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role.permissions


def add_permissions_to_role(db: Session, role_id: UUID, permissions: list) -> Role:
    """
    Add permissions to a role.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Ensure no duplicates
    existing_permissions = set(role.permissions)
    new_permissions = set(permissions)
    
    if new_permissions.issubset(existing_permissions):
        raise HTTPException(status_code=400, detail="These permissions are already assigned to the role.")
    
    # Update the permissions
    role.permissions.extend(list(new_permissions - existing_permissions))
    
    db.commit()
    db.refresh(role)
    return role


def remove_permissions_from_role(db: Session, role_id: UUID, permissions: list) -> Role:
    """
    Remove permissions from a role.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Ensure the permissions to be removed exist
    existing_permissions = set(role.permissions)
    permissions_to_remove = set(permissions)
    
    if not permissions_to_remove.issubset(existing_permissions):
        raise HTTPException(status_code=400, detail="Some permissions do not exist in the role.")
    
    # Update the permissions
    role.permissions = list(existing_permissions - permissions_to_remove)
    
    db.commit()
    db.refresh(role)
    return role

def get_role_by_name(db: Session, role_name: str, organization_id: UUID) -> Role:
    """
    Retrieve a role by its name within a specific organization.
    """
    role = db.query(Role).filter(
        Role.name == role_name,
        Role.organization_id == organization_id
    ).first()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role

def get_roles_by_user(db: Session, user_id: UUID) -> list:
    """
    Retrieve all roles assigned to a specific user.
    """
    roles = db.query(Role).filter(Role.user_id == user_id).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found for this user")
    
    return roles

def assign_role_to_user(db: Session, user_id: UUID, role_id: UUID) -> Role:
    """
    Assign a specific role to a user.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Assuming there's a many-to-many relationship between users and roles
    role.users.append(user_id)
    
    db.commit()
    db.refresh(role)
    return role

def remove_role_from_user(db: Session, user_id: UUID, role_id: UUID) -> Role:
    """
    Remove a specific role from a user.
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Assuming there's a many-to-many relationship between users and roles
    role.users.remove(user_id)
    
    db.commit()
    db.refresh(role)
    return role

def get_roles_by_permission_within_an_organization(db: Session, permission: str, organization_id: UUID) -> list:
    """
    Retrieve all roles that have a specific permission for a given o.
    """
    roles = db.query(Role).filter(Role.permissions.contains(permission), Role.organization_id == organization_id).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found with this permission")
    
    return roles

def get_roles_by_permission(db: Session, permission: str) -> list:
    """
    Retrieve all roles that have a specific permission.
    """
    roles = db.query(Role).filter(Role.permissions.contains(permission)).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found with this permission")
    
    return roles

def get_role_by_name_and_org(db: Session, role_name: str, organization_id: UUID) -> Role:
    """
    Retrieve a role by its name within a specific organization.
    """
    role = db.query(Role).filter(
        Role.name == role_name,
        Role.organization_id == organization_id
    ).first()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role

def get_roles_by_user_and_org(db: Session, user_id: UUID, organization_id: UUID) -> list:
    """
    Retrieve all roles assigned to a specific user within a specific organization.
    """
    roles = db.query(Role).filter(
        Role.user_id == user_id,
        Role.organization_id == organization_id
    ).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found for this user in this organization")
    
    return roles

def get_roles_by_user_and_org_with_permissions(db: Session, user_id: UUID, organization_id: UUID) -> list:
    """
    Retrieve all roles assigned to a specific user within a specific organization, including permissions.
    """
    roles = db.query(Role).filter(
        Role.user_id == user_id,
        Role.organization_id == organization_id
    ).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found for this user in this organization")
    
    return [{"role": role.name, "permissions": role.permissions} for role in roles]

def get_roles_by_org_with_permissions(db: Session, organization_id: UUID) -> list:
    """
    Retrieve all roles within a specific organization, including permissions.
    """
    roles = db.query(Role).filter(Role.organization_id == organization_id).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found in this organization")
    
    return [{"role": role.name, "permissions": role.permissions} for role in roles]

def get_role_by_name_and_org_id(db: Session, role_name: str, organization_id: UUID) -> Role:
    """
    Retrieve a role by its name within a specific organization.
    """
    role = db.query(Role).filter(
        Role.name == role_name,
        Role.organization_id == organization_id
    ).first()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role

def get_roles_by_org_id(db: Session, organization_id: UUID) -> list:
    """
    Retrieve all roles within a specific organization.
    """
    roles = db.query(Role).filter(Role.organization_id == organization_id).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found in this organization")
    
    return roles

def get_roles_by_org_id_with_permissions(db: Session, organization_id: UUID) -> list:
    """
    Retrieve all roles within a specific organization, including permissions.
    """
    roles = db.query(Role).filter(Role.organization_id == organization_id).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found in this organization")
    
    return [{"role": role.name, "permissions": role.permissions} for role in roles]


def get_roles_by_org_id_with_permissions_and_users(db: Session, organization_id: UUID) -> list:
    """
    Retrieve all roles within a specific organization, including permissions and users.
    """
    roles = db.query(Role).filter(Role.organization_id == organization_id).all()
    
    if not roles:
        raise HTTPException(status_code=404, detail="No roles found in this organization")
    
    return [{"role": role.name, "permissions": role.permissions, "users": role.users} for role in roles]



def get_role_by_id_and_org_id(db: Session, role_id: UUID, organization_id: UUID) -> Role:
    """
    Retrieve a role by its ID within a specific organization.
    """
    role = db.query(Role).filter(
        Role.id == role_id,
        Role.organization_id == organization_id
    ).first()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role