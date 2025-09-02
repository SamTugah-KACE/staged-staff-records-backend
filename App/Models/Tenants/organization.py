from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Date, DECIMAL, Table, create_engine
from sqlalchemy.dialects.postgresql import UUID as SQLUUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.db_session import BaseModel
# import uuid
from fastapi import HTTPException



class Organization(BaseModel):
    __tablename__ = "organizations"

    name = Column(String, nullable=False, unique=True)
    org_email = Column(String, nullable=False, unique=True)
    country = Column(String, nullable=False)
    type = Column(String, nullable=False)  # Private, Government or Public, and NGO 
    nature = Column(String, nullable=False)  # Single, Networked
    employee_range = Column(String, nullable=False)  # e.g., 0-10
    logos = Column(JSONB, nullable=True)  # Store logo paths
    access_url = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    subscription_plan = Column(String, nullable=False, default="Basic")  # Basic, Premium
  

   

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete")
    roles = relationship("Role", back_populates="organization", cascade="all, delete")
    files = relationship("FileStorage", back_populates="organization", cascade="all, delete")
    tenancies = relationship("Tenancy", back_populates="organization", cascade="all, delete")
    settings = relationship("SystemSetting", back_populates="organization", cascade="all, delete")
    dashboards = relationship("Dashboard", back_populates="organization", cascade="all, delete")
    employees = relationship("Employee", back_populates="organization", cascade="all, delete-orphan")
    branches = relationship("Branch", back_populates="organization", cascade="all, delete")
    departments = relationship("Department", back_populates="organization", cascade="all, delete")
    ranks = relationship("Rank", back_populates="organization", cascade="all, delete")
    employee_types = relationship("EmployeeType", back_populates="organization")
    promotion_policies = relationship("PromotionPolicy", back_populates="organization")
    clients = relationship("Client", back_populates="organization")

   
    # Method to enforce active organization
    @staticmethod
    def check_organization_active(org_id: SQLUUID, db):
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        if not organization or not organization.is_active:
            raise HTTPException(status_code=403, detail="Organization is inactive.")
    
    def is_organization_active(self):
        return self.is_active


    @staticmethod
    def toggle_active_status(org_id, new_status, db):
        """Toggle active status of an organization."""
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        if not organization:
            raise HTTPException(status_code=404, detail="Organization not found.")
        organization.is_active = new_status
        db.commit()



#Branches
class Branch(BaseModel):
    __tablename__ = "branches"
    
    name = Column(String, nullable=False)
    location = Column(String, nullable=False)
    # manager_id points to an Employee (staff) rather than a user.
    manager_id = Column(SQLUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    

    organization = relationship("Organization", back_populates="branches")
    manager = relationship("Employee", foreign_keys=[manager_id])
    departments = relationship("Department", back_populates="branch", cascade="all, delete")


###############################
# 1. Rank & Salary Definitions
###############################

class Rank(BaseModel):
    __tablename__ = "ranks"

    organization_id = Column(SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)  # e.g., "Junior Developer", "Manager"
    min_salary = Column(DECIMAL(precision=10, scale=2), nullable=False)
    max_salary = Column(DECIMAL(precision=10, scale=2), nullable=True)  # Optional maximum
    currency = Column(String, nullable=False, default="GHS")  # Base currency for this rank
    # Optionally store conversion or extra info in a JSON field (could be refreshed via an external API)
    conversion_info = Column(JSONB, nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="ranks")
    employees = relationship("Employee", back_populates="rank")

# ---------------------------
# Promotion Policy & Record
# ---------------------------
class PromotionPolicy(BaseModel):
    __tablename__ = "promotion_policies"
    # A policy might be defined at the organization level.
    organization_id = Column(SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    policy_name = Column(String, nullable=False)
    # period_years = Column(String, nullable=False)  # e.g., "4" (years)
    # JSON field to store criteria rules (e.g., {"min_years_of_service": 3, "min_performance_rating": 4.5})
    criteria = Column(JSONB, nullable=False)  # e.g., performance metrics, minimum tenure, etc. 
    supporting_document_template = Column(String, nullable=True)  # URL or file reference for a template document
    is_active = Column(Boolean, default=True)
    
    organization = relationship("Organization", back_populates="promotion_policies")



class Tenancy(BaseModel):
    __tablename__ = "tenancies"

    organization_id = Column(SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    billing_cycle = Column(String, nullable=False, default="Monthly")  # Monthly, Annually
    terms_and_conditions_id = Column(SQLUUID(as_uuid=True), ForeignKey("terms_and_conditions.id", ondelete="CASCADE", onupdate="CASCADE"))
    status = Column(String, default="Active")  # Active, Terminated, Pending

    # Relationships
    organization = relationship("Organization", back_populates="tenancies")
    terms_and_conditions = relationship("TermsAndConditions", back_populates="tenancies")
    bills = relationship("Bill", back_populates="tenancy", cascade="all, delete, delete-orphan")



class TermsAndConditions(BaseModel):
    __tablename__ = "terms_and_conditions"

    title = Column(String, nullable=False)
    content = Column(JSONB, nullable=False)  # Flexibility for dynamic content  # Store T&Cs as JSON for flexibility
    version = Column(String, nullable=False)  # For historical tracking
    is_active = Column(Boolean, default=True)

    # Relationships
    tenancies = relationship("Tenancy", back_populates="terms_and_conditions")



class Bill(BaseModel):
    __tablename__ = "bills"

    tenancy_id = Column(SQLUUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    amount = Column(DECIMAL(precision=10, scale=2), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String, default="Unpaid")  # Unpaid, Paid, Overdue

    # Relationships
    tenancy = relationship("Tenancy", back_populates="bills")
    payments = relationship("Payment", back_populates="bill", cascade="all, delete, delete-orphan")


class Payment(BaseModel):
    __tablename__ = "payments"

    bill_id = Column(SQLUUID(as_uuid=True), ForeignKey("bills.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    amount_paid = Column(DECIMAL(precision=10, scale=2), nullable=False)
    payment_date = Column(DateTime(timezone=True), default=func.now())
    payment_method = Column(String, nullable=False)  # Card, Bank Transfer, Mobile Money
    transaction_id = Column(String, unique=True, nullable=False)
    status = Column(String, default="Success")  # Success, Failed, Pending

    # Relationships
    bill = relationship("Bill", back_populates="payments")
