# routers/tenant_apis.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
import uuid
from typing import List
from database.db_session import get_db
from Crud.tenant_crud import (
    create_rank, get_rank, list_ranks, update_rank, delete_rank,
    create_promotion_policy, get_promotion_policy, list_promotion_policies, update_promotion_policy, delete_promotion_policy,
    create_payment_gateway_config, get_payment_gateway_config, list_payment_gateway_configs, update_payment_gateway_config, delete_payment_gateway_config,
    create_notification, get_notification, list_notifications, update_notification, delete_notification,
    create_promotion_request, get_promotion_request, list_promotion_requests, update_promotion_request, delete_promotion_request,
    create_employee_payment_detail, get_employee_payment_detail, list_employee_payment_details, update_employee_payment_detail, delete_employee_payment_detail,
    create_salary_payment, get_salary_payment, list_salary_payments, update_salary_payment, delete_salary_payment
)
from Schemas.schemas import (
    RankCreate, RankOut, RankUpdate,
    PromotionPolicyCreate, PromotionPolicyOut, PromotionPolicyUpdate,
    PaymentGatewayConfigCreate, PaymentGatewayConfigOut, PaymentGatewayConfigUpdate,
    NotificationCreate, NotificationOut, NotificationUpdate,
    PromotionRequestCreate, PromotionRequestOut, PromotionRequestUpdate,
    EmployeePaymentDetailCreate, EmployeePaymentDetailOut, EmployeePaymentDetailUpdate,
    SalaryPaymentCreate, SalaryPaymentOut, SalaryPaymentUpdate
)
# Import the production get_current_user dependency
from Crud.auth import get_current_user

# Dummy current user dependency (replace with your real auth)
# def get_current_active_user():
#     class User:
#         id = uuid.uuid4()
#         organization_id = uuid.uuid4()  # Replace with actual organization ID
#     return User()

router = APIRouter()

# --- Rank Endpoints ---
@router.post("/ranks/", response_model=RankOut, status_code=status.HTTP_201_CREATED, tags=["Organization Specific Ranks"])
def api_create_rank(rank_in: RankCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Use the organization from the decoded token
    data = rank_in.dict()
    data["organization_id"] = current_user["user"].organization_id
    return create_rank(db, rank_in=RankCreate(**data))

@router.get("/ranks/", response_model=List[RankOut], tags=["Organization Specific Ranks"])
def api_list_ranks(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return list_ranks(db, organization_id=current_user["user"].organization_id)

@router.get("/ranks/{rank_id}", response_model=RankOut, tags=["Organization Specific Ranks"])
def api_get_rank(rank_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_rank(db, rank_id=rank_id, organization_id=current_user["user"].organization_id)

@router.put("/ranks/{rank_id}", response_model=RankOut, tags=["Organization Specific Ranks"])
def api_update_rank(rank_id: uuid.UUID, rank_in: RankUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return update_rank(db, rank_id=rank_id, organization_id=current_user["user"].organization_id, rank_in=rank_in)

@router.delete("/ranks/{rank_id}", response_model=RankOut, tags=["Organization Specific Ranks"])
def api_delete_rank(rank_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_rank(db, rank_id=rank_id, organization_id=current_user["user"].organization_id)

# --- PromotionPolicy Endpoints ---
@router.post("/promotion-policies/", response_model=PromotionPolicyOut, status_code=status.HTTP_201_CREATED, tags=["Organizational Promotion Policies"])
def api_create_promotion_policy(policy_in: PromotionPolicyCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    data = policy_in.dict()
    data["organization_id"] = current_user["user"].organization_id
    return create_promotion_policy(db, policy_in=PromotionPolicyCreate(**data))

@router.get("/promotion-policies/", response_model=List[PromotionPolicyOut], tags=["Organizational Promotion Policies"])
def api_list_promotion_policies(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return list_promotion_policies(db, organization_id=current_user["user"].organization_id)

@router.get("/promotion-policies/{policy_id}", response_model=PromotionPolicyOut, tags=["Organizational Promotion Policies"])
def api_get_promotion_policy(policy_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_promotion_policy(db, policy_id=policy_id, organization_id=current_user["user"].organization_id)

@router.put("/promotion-policies/{policy_id}", response_model=PromotionPolicyOut, tags=["Organizational Promotion Policies"])
def api_update_promotion_policy(policy_id: uuid.UUID, policy_in: PromotionPolicyUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return update_promotion_policy(db, policy_id=policy_id, organization_id=current_user["user"].organization_id, policy_in=policy_in)

@router.delete("/promotion-policies/{policy_id}", response_model=PromotionPolicyOut, tags=["Organizational Promotion Policies"])
def api_delete_promotion_policy(policy_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_promotion_policy(db, policy_id=policy_id, organization_id=current_user["user"].organization_id)

# --- PaymentGatewayConfig Endpoints ---
@router.post("/payment-gateway-configs/", response_model=PaymentGatewayConfigOut, status_code=status.HTTP_201_CREATED, tags=["Organizational Payment Gateway Configurations"])
def api_create_payment_gateway_config(config_in: PaymentGatewayConfigCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if config_in.organization_id != current_user["user"].organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return create_payment_gateway_config(db, config_in=config_in)

@router.get("/payment-gateway-configs/", response_model=List[PaymentGatewayConfigOut], tags=["Organizational Payment Gateway Configurations"])
def api_list_payment_gateway_configs(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return list_payment_gateway_configs(db, organization_id=current_user["user"].organization_id)

@router.get("/payment-gateway-configs/{config_id}", response_model=PaymentGatewayConfigOut, tags=["Organizational Payment Gateway Configurations"])
def api_get_payment_gateway_config(config_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_payment_gateway_config(db, config_id=config_id, organization_id=current_user["user"].organization_id)

@router.put("/payment-gateway-configs/{config_id}", response_model=PaymentGatewayConfigOut, tags=["Organizational Payment Gateway Configurations"])
def api_update_payment_gateway_config(config_id: uuid.UUID, config_in: PaymentGatewayConfigUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return update_payment_gateway_config(db, config_id=config_id, organization_id=current_user["user"].organization_id, config_in=config_in)

@router.delete("/payment-gateway-configs/{config_id}", response_model=PaymentGatewayConfigOut, tags=["Organizational Payment Gateway Configurations"])
def api_delete_payment_gateway_config(config_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_payment_gateway_config(db, config_id=config_id, organization_id=current_user["user"].organization_id)

# --- Notification Endpoints ---
@router.post("/notifications/", response_model=NotificationOut, status_code=status.HTTP_201_CREATED, tags=["Organizational Notifications"])
def api_create_notification(notif_in: NotificationCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    data = notif_in.dict()
    data["organization_id"] = current_user["user"].organization_id
    return create_notification(db, notif_in=NotificationCreate(**data))

@router.get("/notifications/", response_model=List[NotificationOut], tags=["Organizational Notifications"])
def api_list_notifications(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return list_notifications(db, organization_id=current_user["user"].organization_id)

@router.get("/notifications/{notif_id}", response_model=NotificationOut, tags=["Organizational Notifications"])
def api_get_notification(notif_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_notification(db, notif_id=notif_id, organization_id=current_user["user"].organization_id)

@router.patch("/notifications/{notif_id}", response_model=NotificationOut, tags=["Organizational Notifications"])
def api_update_notification(notif_id: uuid.UUID, notif_in: NotificationUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return update_notification(db, notif_id=notif_id, organization_id=current_user["user"].organization_id, notif_in=notif_in)

@router.delete("/notifications/{notif_id}", response_model=NotificationOut, tags=["Organizational Notifications"])
def api_delete_notification(notif_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_notification(db, notif_id=notif_id, organization_id=current_user["user"].organization_id)

# --- PromotionRequest Endpoints ---
@router.post("/promotion-requests/", response_model=PromotionRequestOut, status_code=status.HTTP_201_CREATED, tags=["Organizational Promotion Requests"])
def api_create_promotion_request(req_in: PromotionRequestCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return create_promotion_request(db, req_in=req_in)

@router.get("/promotion-requests/", response_model=List[PromotionRequestOut], tags=["Organizational Promotion Requests"])
def api_list_promotion_requests(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return list_promotion_requests(db, organization_id=current_user["user"].organization_id)

@router.get("/promotion-requests/{req_id}", response_model=PromotionRequestOut, tags=["Organizational Promotion Requests"])
def api_get_promotion_request(req_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_promotion_request(db, req_id=req_id, organization_id=current_user["user"].organization_id)

@router.patch("/promotion-requests/{req_id}", response_model=PromotionRequestOut, tags=["Organizational Promotion Requests"])
def api_update_promotion_request(req_id: uuid.UUID, req_in: PromotionRequestUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return update_promotion_request(db, req_id=req_id, organization_id=current_user["user"].organization_id, req_in=req_in)

@router.delete("/promotion-requests/{req_id}", response_model=PromotionRequestOut, tags=["Organizational Promotion Requests"])
def api_delete_promotion_request(req_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_promotion_request(db, req_id=req_id, organization_id=current_user["user"].organization_id)

# --- EmployeePaymentDetail Endpoints ---
@router.post("/employee-payment-details/", response_model=EmployeePaymentDetailOut, status_code=status.HTTP_201_CREATED, tags=["Employee Bank|Payment Details"])
def api_create_employee_payment_detail(detail_in: EmployeePaymentDetailCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return create_employee_payment_detail(db, detail_in=detail_in)

@router.get("/employee-payment-details/", response_model=List[EmployeePaymentDetailOut], tags=["Employee Bank|Payment Details"])
def api_list_employee_payment_details(employee_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return list_employee_payment_details(db, employee_id=employee_id)

@router.get("/employee-payment-details/{detail_id}", response_model=EmployeePaymentDetailOut, tags=["Employee Bank|Payment Details"])
def api_get_employee_payment_detail(detail_id: uuid.UUID, employee_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_employee_payment_detail(db, detail_id=detail_id, employee_id=employee_id)

@router.patch("/employee-payment-details/{detail_id}", response_model=EmployeePaymentDetailOut, tags=["Employee Bank|Payment Details"])
def api_update_employee_payment_detail(detail_id: uuid.UUID, employee_id: uuid.UUID, detail_in: EmployeePaymentDetailUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return update_employee_payment_detail(db, detail_id=detail_id, employee_id=employee_id, detail_in=detail_in)

@router.delete("/employee-payment-details/{detail_id}", response_model=EmployeePaymentDetailOut, tags=["Employee Bank|Payment Details"])
def api_delete_employee_payment_detail(detail_id: uuid.UUID, employee_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_employee_payment_detail(db, detail_id=detail_id, employee_id=employee_id)

# --- SalaryPayment Endpoints ---
@router.post("/salary-payments/", response_model=SalaryPaymentOut, status_code=status.HTTP_201_CREATED, tags=["Organizational Specific Salary Payments"])
def api_create_salary_payment(payment_in: SalaryPaymentCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return create_salary_payment(db, payment_in=payment_in)

@router.get("/salary-payments/", response_model=List[SalaryPaymentOut], tags=["Organizational Specific Salary Payments"])
def api_list_salary_payments(employee_id: uuid.UUID = None, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return list_salary_payments(db, employee_id=employee_id)

@router.get("/salary-payments/{payment_id}", response_model=SalaryPaymentOut, tags=["Organizational Specific Salary Payments"])
def api_get_salary_payment(payment_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_salary_payment(db, payment_id=payment_id)

@router.patch("/salary-payments/{payment_id}", response_model=SalaryPaymentOut, tags=["Organizational Specific Salary Payments"])
def api_update_salary_payment(payment_id: uuid.UUID, payment_in: SalaryPaymentUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return update_salary_payment(db, payment_id=payment_id, payment_in=payment_in)

@router.delete("/salary-payments/{payment_id}", response_model=SalaryPaymentOut, tags=["Organizational Specific Salary Payments"])
def api_delete_salary_payment(payment_id: uuid.UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_salary_payment(db, payment_id=payment_id)
