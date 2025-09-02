# crud/tenant_crud.py

from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import List
from Models.Tenants.organization import Rank, PromotionPolicy
from Models.models import (
    PaymentGatewayConfig, Notification, PromotionRequest, 
    EmployeePaymentDetail, SalaryPayment
)

from Schemas.schemas import (
    RankCreate, RankUpdate,
    PromotionPolicyCreate, PromotionPolicyUpdate,
    PaymentGatewayConfigCreate, PaymentGatewayConfigUpdate,
    NotificationCreate, NotificationUpdate,
    PromotionRequestCreate, PromotionRequestUpdate,
    EmployeePaymentDetailCreate, EmployeePaymentDetailUpdate,
    SalaryPaymentCreate, SalaryPaymentUpdate
)

# --- Rank CRUD ---
def create_rank(db: Session, rank_in: RankCreate) -> Rank:
    db_rank = Rank(**rank_in.dict())
    db.add(db_rank)
    db.commit()
    db.refresh(db_rank)
    return db_rank

def get_rank(db: Session, rank_id, organization_id) -> Rank:
    rank = db.query(Rank).filter(Rank.id == rank_id, Rank.organization_id == organization_id).first()
    if not rank:
        raise HTTPException(status_code=404, detail="Rank not found")
    return rank

def list_ranks(db: Session, organization_id) -> List[Rank]:
    return db.query(Rank).filter(Rank.organization_id == organization_id).all()

def update_rank(db: Session, rank_id, organization_id, rank_in: RankUpdate) -> Rank:
    rank = get_rank(db, rank_id, organization_id)
    for field, value in rank_in.dict(exclude_unset=True).items():
        setattr(rank, field, value)
    db.commit()
    db.refresh(rank)
    return rank

def delete_rank(db: Session, rank_id, organization_id) -> Rank:
    rank = get_rank(db, rank_id, organization_id)
    db.delete(rank)
    db.commit()
    return rank

# --- PromotionPolicy CRUD ---
def create_promotion_policy(db: Session, policy_in: PromotionPolicyCreate) -> PromotionPolicy:
    db_policy = PromotionPolicy(**policy_in.dict())
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    return db_policy

def get_promotion_policy(db: Session, policy_id, organization_id) -> PromotionPolicy:
    policy = db.query(PromotionPolicy).filter(
        PromotionPolicy.id == policy_id,
        PromotionPolicy.organization_id == organization_id
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="PromotionPolicy not found")
    return policy

def list_promotion_policies(db: Session, organization_id) -> List[PromotionPolicy]:
    return db.query(PromotionPolicy).filter(PromotionPolicy.organization_id == organization_id).all()

def update_promotion_policy(db: Session, policy_id, organization_id, policy_in: PromotionPolicyUpdate) -> PromotionPolicy:
    policy = get_promotion_policy(db, policy_id, organization_id)
    for field, value in policy_in.dict(exclude_unset=True).items():
        setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    return policy

def delete_promotion_policy(db: Session, policy_id, organization_id) -> PromotionPolicy:
    policy = get_promotion_policy(db, policy_id, organization_id)
    db.delete(policy)
    db.commit()
    return policy

# --- PaymentGatewayConfig CRUD ---
def create_payment_gateway_config(db: Session, config_in: PaymentGatewayConfigCreate) -> PaymentGatewayConfig:
    db_config = PaymentGatewayConfig(**config_in.dict())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

def get_payment_gateway_config(db: Session, config_id, organization_id) -> PaymentGatewayConfig:
    config = db.query(PaymentGatewayConfig).filter(
        PaymentGatewayConfig.id == config_id,
        PaymentGatewayConfig.organization_id == organization_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="PaymentGatewayConfig not found")
    return config

def list_payment_gateway_configs(db: Session, organization_id) -> List[PaymentGatewayConfig]:
    return db.query(PaymentGatewayConfig).filter(PaymentGatewayConfig.organization_id == organization_id).all()

def update_payment_gateway_config(db: Session, config_id, organization_id, config_in: PaymentGatewayConfigUpdate) -> PaymentGatewayConfig:
    config = get_payment_gateway_config(db, config_id, organization_id)
    for field, value in config_in.dict(exclude_unset=True).items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config

def delete_payment_gateway_config(db: Session, config_id, organization_id) -> PaymentGatewayConfig:
    config = get_payment_gateway_config(db, config_id, organization_id)
    db.delete(config)
    db.commit()
    return config

# --- Notification CRUD ---
def create_notification(db: Session, notif_in: NotificationCreate) -> Notification:
    db_notif = Notification(**notif_in.dict())
    db.add(db_notif)
    db.commit()
    db.refresh(db_notif)
    return db_notif

def get_notification(db: Session, notif_id, organization_id) -> Notification:
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.organization_id == organization_id
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notif

def list_notifications(db: Session, organization_id) -> List[Notification]:
    return db.query(Notification).filter(Notification.organization_id == organization_id).all()

def update_notification(db: Session, notif_id, organization_id, notif_in: NotificationUpdate) -> Notification:
    notif = get_notification(db, notif_id, organization_id)
    for field, value in notif_in.dict(exclude_unset=True).items():
        setattr(notif, field, value)
    db.commit()
    db.refresh(notif)
    return notif

def delete_notification(db: Session, notif_id, organization_id) -> Notification:
    notif = get_notification(db, notif_id, organization_id)
    db.delete(notif)
    db.commit()
    return notif

# --- PromotionRequest CRUD ---
def create_promotion_request(db: Session, req_in: PromotionRequestCreate) -> PromotionRequest:
    db_req = PromotionRequest(**req_in.dict())
    db.add(db_req)
    db.commit()
    db.refresh(db_req)
    return db_req

def get_promotion_request(db: Session, req_id, organization_id) -> PromotionRequest:
    req = db.query(PromotionRequest).join("employee").filter(
        PromotionRequest.id == req_id,
        PromotionRequest.employee.has(organization_id=organization_id)
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="PromotionRequest not found")
    return req

def list_promotion_requests(db: Session, organization_id) -> List[PromotionRequest]:
    return db.query(PromotionRequest).join("employee").filter(
        PromotionRequest.employee.has(organization_id=organization_id)
    ).all()

def update_promotion_request(db: Session, req_id, organization_id, req_in: PromotionRequestUpdate) -> PromotionRequest:
    req = get_promotion_request(db, req_id, organization_id)
    for field, value in req_in.dict(exclude_unset=True).items():
        setattr(req, field, value)
    db.commit()
    db.refresh(req)
    return req

def delete_promotion_request(db: Session, req_id, organization_id) -> PromotionRequest:
    req = get_promotion_request(db, req_id, organization_id)
    db.delete(req)
    db.commit()
    return req

# --- EmployeePaymentDetail CRUD ---
def create_employee_payment_detail(db: Session, detail_in: EmployeePaymentDetailCreate) -> EmployeePaymentDetail:
    db_detail = EmployeePaymentDetail(**detail_in.dict())
    db.add(db_detail)
    db.commit()
    db.refresh(db_detail)
    return db_detail

def get_employee_payment_detail(db: Session, detail_id, employee_id) -> EmployeePaymentDetail:
    detail = db.query(EmployeePaymentDetail).filter(
        EmployeePaymentDetail.id == detail_id,
        EmployeePaymentDetail.employee_id == employee_id
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="EmployeePaymentDetail not found")
    return detail

def list_employee_payment_details(db: Session, employee_id) -> List[EmployeePaymentDetail]:
    return db.query(EmployeePaymentDetail).filter(EmployeePaymentDetail.employee_id == employee_id).all()

def update_employee_payment_detail(db: Session, detail_id, employee_id, detail_in: EmployeePaymentDetailUpdate) -> EmployeePaymentDetail:
    detail = get_employee_payment_detail(db, detail_id, employee_id)
    for field, value in detail_in.dict(exclude_unset=True).items():
        setattr(detail, field, value)
    db.commit()
    db.refresh(detail)
    return detail

def delete_employee_payment_detail(db: Session, detail_id, employee_id) -> EmployeePaymentDetail:
    detail = get_employee_payment_detail(db, detail_id, employee_id)
    db.delete(detail)
    db.commit()
    return detail

# --- SalaryPayment CRUD ---
def create_salary_payment(db: Session, payment_in: SalaryPaymentCreate) -> SalaryPayment:
    db_payment = SalaryPayment(**payment_in.dict())
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    return db_payment

def get_salary_payment(db: Session, payment_id) -> SalaryPayment:
    payment = db.query(SalaryPayment).filter(SalaryPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="SalaryPayment not found")
    return payment

def list_salary_payments(db: Session, employee_id: str = None) -> List[SalaryPayment]:
    query = db.query(SalaryPayment)
    if employee_id:
        query = query.filter(SalaryPayment.employee_id == employee_id)
    return query.all()

def update_salary_payment(db: Session, payment_id, payment_in: SalaryPaymentUpdate) -> SalaryPayment:
    payment = get_salary_payment(db, payment_id)
    for field, value in payment_in.dict(exclude_unset=True).items():
        setattr(payment, field, value)
    db.commit()
    db.refresh(payment)
    return payment

def delete_salary_payment(db: Session, payment_id) -> SalaryPayment:
    payment = get_salary_payment(db, payment_id)
    db.delete(payment)
    db.commit()
    return payment