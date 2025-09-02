# routers/promotion_request_api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid
from datetime import datetime
from Models.models import Employee, PromotionRequest, Notification, Department
from database.db_session import get_db

router = APIRouter()

@router.post("/confirm-promotion-request/", status_code=status.HTTP_201_CREATED)
def confirm_promotion_request(employee_id: uuid.UUID, db: Session = Depends(get_db)):
    # Get the employee.
    employee = db.query(Employee).filter(Employee.id == employee_id, Employee.is_active == True).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Insert confirmed promotion request.
    promo_req = PromotionRequest(
        employee_id = employee.id,
        current_rank_id = employee.rank_id,
        request_date = datetime.utcnow(),
        # promotion_effective_date, evidence_documents, and comments can be set by the employee as needed.
    )
    db.add(promo_req)
    db.commit()
    db.refresh(promo_req)

    # Trigger an event: create a notification for the head of department.
    # Assume that employee.department_id exists and the Department model has a department_head_id.
    dept = db.query(Department).filter(Department.id == getattr(employee, "department_id", None)).first()
    if dept and dept.department_head_id:
        hod_notif = Notification(
            organization_id = employee.organization_id,
            user_id = dept.department_head_id,
            type = 'promotion_request',
            message = f"Promotion request from {employee.first_name} {employee.last_name} is pending your review."
        )
        db.add(hod_notif)
        db.commit()

    return {"message": "Promotion request confirmed and notification sent to your Head of Department."}
