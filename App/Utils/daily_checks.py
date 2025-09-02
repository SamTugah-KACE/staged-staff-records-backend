# Utils/daily_checks.py
import asyncio
from datetime import datetime
import os
from sqlalchemy.orm import Session
from database.db_session import SessionLocal
from Models.Tenants.organization import Organization, PromotionPolicy
from Models.models import Employee, Department, PromotionRequest, Notification
from Utils.promotion_evaluator import evaluate_promotion_criteria, is_birthday
import logging

# Import the new log model
from Models.daily_check_log import DailyCheckLog


# APScheduler imports
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore



logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)




def daily_checks(db: Session):
    """Run daily checks for promotion eligibility and birthdays."""
    today = datetime.utcnow().date()
    organizations = db.query(Organization).filter(Organization.is_active == True).all()
    
    for org in organizations:
        # -- Promotion Check --
        policies = org.promotion_policies  # relationship to PromotionPolicy
        for policy in policies:
            if not policy.is_active:
                continue

            # Get all active employees for this organization.
            employees = db.query(Employee).filter(
                Employee.organization_id == org.id,
                Employee.is_active == True
            ).all()

            for emp in employees:
                # Evaluate using the dynamic criteria.
                if evaluate_promotion_criteria(policy.criteria, emp):
                    # Check if a promotion_due notification already exists (avoid duplicates)
                    exists = db.query(Notification).filter(
                        Notification.employee_id == emp.id,
                        Notification.type == 'promotion_due',
                        Notification.is_read == False
                    ).first()
                    if not exists:
                        notif = Notification(
                            organization_id = org.id,
                            employee_id = emp.id,
                            type = 'promotion_due',
                            message = (
                                f"Hi {emp.first_name}, based on the {policy.policy_name} policy, "
                                "you are due for promotion. Please confirm if you wish to submit a promotion request."
                            )
                        )
                        db.add(notif)
                        db.commit()

        # -- Birthday Check --
        employees_with_birthday = db.query(Employee).filter(
            Employee.organization_id == org.id,
            Employee.date_of_birth.isnot(None)
        ).all()
        for emp in employees_with_birthday:
            if emp.date_of_birth.month == today.month and emp.date_of_birth.day == today.day:
                # Create a birthday notification for the employee.
                birthday_notif = Notification(
                    organization_id = org.id,
                    employee_id = emp.id,
                    type = 'birthday',
                    message = f"Happy Birthday, {emp.first_name}! Have a great day!"
                )
                db.add(birthday_notif)
                # Also notify the head of department and colleagues if desired.
                # For example, if the employee is assigned a department:
                if hasattr(emp, "department_id") and emp.department_id:
                    dept = db.query(Department).filter(Department.id == emp.department_id).first()
                    if dept and dept.department_head_id:
                        hod_notif = Notification(
                            organization_id = org.id,
                            user_id = dept.department_head_id,
                            type = 'birthday_team',
                            message = f"{emp.first_name} {emp.last_name} is celebrating a birthday today!"
                        )
                        db.add(hod_notif)
        db.commit()


def daily_checks_wrapper():
    """Wrapper to create a DB session and run daily_checks."""
    try:
        with SessionLocal() as db:
            today = datetime.utcnow().date()
            # Check if the daily check for today is already logged.
            log_entry = db.query(DailyCheckLog).filter(DailyCheckLog.check_date == today).first()
            if log_entry:
                logger.info("Daily checks already executed for today: %s", today)
                return
            # Run the daily checks.
            daily_checks(db)
            # Log today's check to prevent duplicate runs.
            new_log = DailyCheckLog(check_date=today)
            db.add(new_log)
            db.commit()
        logger.info("Daily checks executed successfully for date: %s", today)
    except Exception as e:
        logger.exception("Error executing daily checks: %s", e)

def schedule_daily_checks():
    """
    Configure and start the APScheduler to run daily_checks_wrapper every 24 hours.
    Uses SQLAlchemyJobStore to persist job definitions in your database.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL is not configured in the environment.")
        raise RuntimeError("DATABASE_URL is required for scheduling jobs.")

    jobstores = {
        'default': SQLAlchemyJobStore(url=db_url)
    }
    scheduler = AsyncIOScheduler(jobstores=jobstores)
    scheduler.add_job(daily_checks_wrapper, trigger='interval', days=1, id='daily_checks', replace_existing=True)
    scheduler.start()
    logger.info("APScheduler started with daily checks job.")
    return scheduler