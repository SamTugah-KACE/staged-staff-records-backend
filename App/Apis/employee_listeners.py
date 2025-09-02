# src/api/employee_listeners.py
import asyncio
import json
from sqlalchemy import event
from sqlalchemy.orm import Session

# List all models whose changes should trigger employee data updates
# We'll import these lazily to avoid circular imports
EMPLOYEE_RELATED_MODELS = None

async def broadcast_employee_update(employee_id: str, organization_id: str, db: Session):
    """
    Rebuild the employee data for employee_id and broadcast an 'update' to all connected sockets.
    """
    try:
        # Lazy import to avoid circular imports
        from Service.employee_aggregator import get_employee_full_record
        from notification.socket import manager
        
        # Get the updated employee data
        updated_data = get_employee_full_record(db, employee_id)
        
        # Create the update message
        message = {
            "type": "update", 
            "payload": updated_data,
            "employee_id": employee_id
        }
        
        # Broadcast to all users in the organization who are connected to this employee's data
        # We'll broadcast to the organization and let the client filter by employee_id
        await manager.broadcast_json(organization_id, message)
        
        print(f"✅ Broadcasted employee update for employee_id: {employee_id} to org: {organization_id}")
        
    except Exception as e:
        print(f"❌ Error broadcasting employee update for {employee_id}: {e}")

def _after_employee_change(mapper, connection, target):
    """
    This handler runs when any employee-related data changes.
    It triggers a broadcast of the updated employee data.
    """
    try:
        # Get the session from connection info
        db: Session = connection.info.get("session")
        if db is None:
            print("❌ No session found in connection.info, cannot broadcast employee update")
            return
            
        # Determine the employee_id and organization_id
        employee_id = None
        organization_id = None
        
        if mapper.class_ == Employee:
            # Direct employee update
            employee_id = str(target.id)
            organization_id = str(target.organization_id)
        else:
            # Related model update - get employee_id from the relationship
            if hasattr(target, 'employee_id'):
                employee_id = str(target.employee_id)
                # Get organization_id from the employee
                emp_result = connection.execute(
                    f"SELECT organization_id FROM employees WHERE id = '{employee_id}'"
                ).first()
                if emp_result:
                    organization_id = str(emp_result[0])
            elif hasattr(target, 'employee'):
                # If it's a relationship object
                if target.employee:
                    employee_id = str(target.employee.id)
                    organization_id = str(target.employee.organization_id)
        
        if employee_id and organization_id:
            # Broadcast the update without blocking the current transaction
            asyncio.get_event_loop().create_task(
                broadcast_employee_update(employee_id, organization_id, db)
            )
        else:
            print(f"❌ Could not determine employee_id or organization_id for {mapper.class_.__name__}")
            
    except Exception as e:
        print(f"❌ Error in employee change listener: {e}")

def register_employee_listeners():
    """
    Register database event listeners for all employee-related models.
    This should be called during application startup.
    """
    global EMPLOYEE_RELATED_MODELS
    
    # Lazy import to avoid circular imports
    from Models.models import (
        Employee, 
        AcademicQualification, 
        ProfessionalQualification,
        EmploymentHistory, 
        EmergencyContact, 
        NextOfKin,
        EmployeeDataInput,
        SalaryPayment,
        PromotionRequest
    )
    from Models.dynamic_models import EmployeeDynamicData
    
    EMPLOYEE_RELATED_MODELS = [
        Employee,
        AcademicQualification,
        ProfessionalQualification, 
        EmploymentHistory,
        EmergencyContact,
        NextOfKin,
        EmployeeDataInput,
        SalaryPayment,
        PromotionRequest,
        EmployeeDynamicData
    ]
    
    for model in EMPLOYEE_RELATED_MODELS:
        # Listen for insert, update, and delete events
        event.listen(model, "after_insert", _after_employee_change)
        event.listen(model, "after_update", _after_employee_change)
        event.listen(model, "after_delete", _after_employee_change)
        
    print(f"✅ Registered employee listeners for {len(EMPLOYEE_RELATED_MODELS)} models")

def unregister_employee_listeners():
    """
    Unregister all employee listeners.
    This can be called during application shutdown.
    """
    global EMPLOYEE_RELATED_MODELS
    
    if EMPLOYEE_RELATED_MODELS:
        for model in EMPLOYEE_RELATED_MODELS:
            event.remove(model, "after_insert", _after_employee_change)
            event.remove(model, "after_update", _after_employee_change)
            event.remove(model, "after_delete", _after_employee_change)
            
    print("✅ Unregistered all employee listeners")
