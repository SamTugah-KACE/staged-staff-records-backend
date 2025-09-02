# src/services/employee_aggregator.py
from sqlalchemy.orm import Session, joinedload
from Models.models import (
    Employee,
    AcademicQualification,
    ProfessionalQualification,
    EmploymentHistory,
    EmergencyContact,
    NextOfKin,
    PromotionRequest,
    Department,
    EmployeeType,
    SalaryPayment,
    EmployeePaymentDetail,
)
from Models.dynamic_models import EmployeeDynamicData
from Models.Tenants.organization import Organization, Rank
from Models.Tenants.role import Role
from Models.models import User
from typing import Dict, Any

def get_employee_full_record(db: Session, employee_id: str) -> Dict[str, Any]:
    """
    Load all related data for the given employee_id and
    return a nested dict keyed by the categories you specified.
    """
    # Eager-load relationships to minimize SQL round-trips:
    emp = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .options(
            joinedload(Employee.academic_qualifications),
            joinedload(Employee.professional_qualifications),
            joinedload(Employee.employment_history),
            joinedload(Employee.emergency_contacts),
            joinedload(Employee.next_of_kins),
            joinedload(Employee.promotion_requests),
            joinedload(Employee.salary_payments),
            joinedload(Employee.payment_details),
            joinedload(Employee.employee_type),
            joinedload(Employee.rank),
            joinedload(Employee.department).joinedload(Department.branch),
            #joinedload(Employee.organization).joinedload(Role.users),  # for Role via user->role
            joinedload(Employee.dynamic_data),
        )
        .first()
    )
    if not emp:
        return {}
    
     # fetch the corresponding User by email
    user = db.query(User).filter(User.email == emp.email).options(
        joinedload(User.role)
    ).first()

    org_type = None
    #fetch organization details
    if emp.organization:
        emp.organization = db.query(Organization).filter(Organization.id == emp.organization_id).first()
        #check type of organization whether it is Private or Public or Government or NGO
        if emp.organization.type == "Private":
            org_type = "Private"
        elif emp.organization.type == "Public":
            org_type = "Public"
        elif emp.organization.type == "Government":
            org_type = "Government"
        elif emp.organization.type == "NGO":
            org_type = "NGO"

    # Build structure
    out = {
        "Bio-data": {
            "first_name": emp.first_name,
            "middle_name": emp.middle_name,
            "last_name": emp.last_name,
            "title": emp.title,
            "gender": emp.gender,
            "date_of_birth": emp.date_of_birth.isoformat() if emp.date_of_birth else None,
            "marital_status": emp.marital_status,
            "email": emp.email,
            "contact_info": emp.contact_info,
            "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
            "termination_date": emp.termination_date.isoformat() if emp.termination_date else None,
            "profile_image_path": emp.profile_image_path,
        },
        "Qualifications": {
            "Academic-qualifications": [
                {
                    "id": q.id,
                    "degree": q.degree,
                    "institution": q.institution,
                    "year_obtained": q.year_obtained,
                    "details": q.details,
                    "certificate_path": q.certificate_path,
                }
                for q in emp.academic_qualifications
            ],
            "Professional-qualifications": [
                {
                    "id": q.id,
                    "qualification_name": q.qualification_name,
                    "institution": q.institution,
                    "year_obtained": q.year_obtained,
                    "details": q.details,
                    "license_path": q.license_path,
                }
                for q in emp.professional_qualifications
            ],
        },
        "Employment-details": {
            "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
            "termination_date": emp.termination_date.isoformat() if emp.termination_date else None,
            "rank": {
                "id": emp.rank.id,
                "name": emp.rank.name,
                "min_salary": str(emp.rank.min_salary),
                "max_salary": str(emp.rank.max_salary) if emp.rank.max_salary else None,
                "currency": emp.rank.currency,
            } if emp.rank else {},
            "employee-type": {
                "id": emp.employee_type.id,
                "type_code": emp.employee_type.type_code,
                "description": emp.employee_type.description,
            } if emp.employee_type else {},
            "department": {
                "id": emp.department.id,
                "name": emp.department.name,
                **(
                    {
                        "branch": {
                            "id": emp.department.branch.id,
                            "name": emp.department.branch.name,
                            "location": emp.department.branch.location,
                        }
                    }
                    if emp.department.branch
                    else {}
                ),
            } if emp.department else {},
        },
        "Role": {
            "id": user.role.id,
            "name": user.role.name,
            "permissions": user.role.permissions,
        } if user and user.role else {},
        "Payment-details": [
            {
                "id": p.id,
                "payment_mode": p.payment_mode,
                "bank_name": p.bank_name,
                "account_number": p.account_number,
                "mobile_money_provider": p.mobile_money_provider,
                "wallet_number": p.wallet_number,
                "additional_info": p.additional_info,
                "is_verified": p.is_verified,
            }
            for p in emp.payment_details
        ],
        "Promotions": [
            {
                "id": pr.id,
                "current_rank_id": pr.current_rank_id,
                "proposed_rank_id": pr.proposed_rank_id,
                "request_date": pr.request_date.isoformat(),
                "promotion_effective_date": pr.promotion_effective_date.isoformat() if pr.promotion_effective_date else None,
                "department_approved": pr.department_approved,
                "hr_approved": pr.hr_approved,
                "evidence_documents": pr.evidence_documents,
                "comments": pr.comments,
            }
            for pr in emp.promotion_requests
        ],
        "Next-of-kin": [
            {"id": nk.id, "name": nk.name, "relation": nk.relation, "nok_phone": nk.nok_phone, "nok_address": nk.nok_address, "details": nk.details}
            for nk in emp.next_of_kins
        ],
        "Emergency-contacts": [
            {"id": ec.id, "name": ec.name, "relation": ec.relation, "emergency_phone": ec.emergency_phone, "emergency_address": ec.emergency_address, "details": ec.details}
            for ec in emp.emergency_contacts
        ],
        "Employment-history": [
            {"id": h.id, "job_title": h.job_title, "company": h.company,
             "start_date": h.start_date.isoformat(),
             "end_date": h.end_date.isoformat() if h.end_date else None,
             "details": h.details,
             "documents_path": h.documents_path}
            for h in emp.employment_history
        ],
        #if organization type is not None, and it is Private then fetch salary payments
        "Salary-payments": [
            {
                "id": sp.id,
                "salary_month": sp.salary_month.isoformat(),
                "salary_year": sp.salary_year,
                "amount": str(sp.amount),
                "currency": sp.currency,
                "payment_date": sp.payment_date.isoformat() if sp.payment_date else None,
                "payment_status": sp.payment_status,
            }
            for sp in emp.salary_payments if org_type == "Private"
        ] if org_type == "Private" else {},
        "Others": {
            "custom_data": emp.custom_data if emp.custom_data else {},

            "dynamic_data":{
                d.data_category: d.data for d in emp.dynamic_data
                }
        },
    }

    return out