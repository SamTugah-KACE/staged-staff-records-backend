
from decimal import Decimal
import json
from pydantic import BaseModel, EmailStr, Field, field_validator, root_validator, model_validator
from typing import Any, Optional, List, Dict, Union
from uuid import UUID
from datetime import datetime, date
from enum import Enum


def convert_old_permissions(old: Dict[str, Any]) -> List[str]:
    """
    Converts an old permission dict to a flat list in the new standardized format.
    Update the conversion_map as needed.
    For example:
      { "read": "all", "write": "all", "delete": "all" }
    becomes:
      [ "users:create", "users:delete", "reports:generate", "reports:view" ]
    """
    # Mapping can be updated in the future as needed.
    conversion_map = {
        "read": ["users:create", "users:delete"],
        "write": ["users:delete"],
        "delete": ["reports:generate", "reports:view"]
    }
    result = []
    for key, val in old.items():
        if isinstance(val, str) and val.lower() == "all" and key in conversion_map:
            result.extend(conversion_map[key])
        else:
            # Fallback: simply join key and value with a colon.
            result.append(f"{key}:{val}")
    return result

# Enums
class Gender(str, Enum):
    male = "Male"
    female = "Female"
    other = "Other"

class MaritalStatus(str, Enum):
    single = "Single"
    married = "Married"
    divorced = "Divorced"
    widowed = "Widowed"
    separated = "Separated"
    other = "Other"

class Title(str, Enum):
    prof = 'Prof.'
    phd = 'PhD'
    dr = 'Dr.'
    mr = 'Mr.'
    mrs = 'Mrs.'
    ms = 'Ms.'
    esq = 'Esq.'
    hon = 'Hon.'
    rev = 'Rev.'
    msgr = 'Msgr.'
    sr = 'Sr.'
    other = 'Other'

class BillingCycle(str, Enum):
    monthly = "Monthly"
    mid_year = "Mid-Year"
    annually = "Annually"

class TenancyStatus(str, Enum):
    active = "Active"
    terminated = "Terminated"
    pending = "Pending"

class PaymentStatus(str, Enum):
    unpaid = "Unpaid"
    paid = "Paid"
    overdue = "Overdue"

# Shared Base Schema
class BaseSchema(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_by: Optional[UUID]

    class Config:
        # orm_mode = True
        # Use from_attributes for Pydantic V2 (replacing orm_mode)
        from_attributes = True
        # Ensure that UUID values are serialized as strings.
        json_encoders = {
            UUID: lambda v: str(v)
        }

# Organization Schemas
class OrganizationCreateSchema(BaseModel):
    name: str
    org_email: EmailStr
    country: str
    type: str
    nature: str
    employee_range: str
    access_url: str
    subscription_plan: Optional[str] = "Basic"
    logos: Optional[Dict] = {}
    tenancies:Optional[List["TenancyCreateSchema"]]
    roles: Optional[List["RoleCreateSchema"]] 
    employees: Optional[List["EmployeeCreateSchema"]]
    users: Optional[List["UserCreateSchema"]] 
    # dashboard: Optional[List["DashboardCreateSchema"]]
    settings: Optional[List["SystemSettingCreateSchema"]] = None

    @field_validator("type")
    def validate_type(cls, value):
        if value not in ["Private", "Government", "Public", "NGO"]:
            raise ValueError("Type must be either 'Private', 'NGO', 'Government' or 'Public'")
        return value

class OrganizationSchema(BaseSchema):
    name: str
    org_email: EmailStr
    country: str
    type: str
    nature: str
    employee_range: str
    access_url: str
    subscription_plan: Optional[str]
    is_active: bool
    logos: Optional[Dict] = {}
    users: Optional[List["UserSchema"]] = []
    employees: Optional[List["EmployeeSchema"]] = []
    roles: Optional[List["RoleSchema"]] = []
    tenancies:Optional[List["TenancySchema"]] = []
    # dashboard: Optional[List["DashboardCreateSchema"]]
    settings: Optional[List["SystemSettingSchema"]] = []

    class Config:
        from_attributes = True  # Enable ORM object compatibility

# in Schemas.schemas.py near OrganizationSchema

class OrganizationUpdateSchema(BaseModel):
    name: Optional[str]
    org_email: Optional[EmailStr]
    country: Optional[str]
    type: Optional[str]
    nature: Optional[str]
    employee_range: Optional[str]
    access_url: Optional[str]
    subscription_plan: Optional[str]
    logos: Optional[Dict[str, Any]]
    is_active: Optional[bool]

    @field_validator("type")
    def validate_type(cls, value):
        if value and value not in ["Private", "Government", "Public", "NGO"]:
            raise ValueError("Invalid organization type")
        return value

    class Config:
        from_attributes = True


# Role Schemas
class RoleCreateSchema(BaseModel):
    name: str
    permissions: Optional[Union[List[str], Dict[str, Any]]] = None
    organization_id: Optional[UUID]
    

    @field_validator("name")
    def validate_name(cls, value):
        if not value:
            raise ValueError("Role name cannot be empty")
        return value
    
    @field_validator("permissions")
    @classmethod
    def normalize_permissions(cls, v):
        if isinstance(v, dict):
            # Flatten dictionary keys or keys with True values
            return [key for key, val in v.items() if val is True or val == 1 or val == "1"]
        elif isinstance(v, list):
            if not all(isinstance(i, str) for i in v):
                raise ValueError("All permission list items must be strings")
            return v
        elif v is None:
            return []
        raise ValueError("Permissions must be either a list of strings or a dictionary")

class RoleSchema(BaseSchema):
    name: str
    permissions: Optional[List[str]]
    organization_id: Optional[UUID]

    @field_validator("permissions", mode="before")
    @classmethod
    def normalize_permissions(cls, value):
        if isinstance(value, dict):
            return convert_old_permissions(value)
        if isinstance(value, list):
            return value
        return []

    # class Config:
    #     from_attributes = True
    #     json_encoders = {
    #         UUID: lambda v: str(v)
    #     }

    class Config:
        from_attributes = True


#Branch Schema
class BranchBase(BaseModel):
    name: str
    location: str
    manager_id: Optional[UUID] = None

class BranchCreate(BranchBase):
    pass

class BranchUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    manager_id: Optional[UUID] = None

class BranchOut(BranchBase):
    id: UUID
    organization_id: UUID
    # created_at: datetime

    class Config:
        from_attributes = True





#Departments
class DepartmentBase(BaseModel):
    name: str
    department_head_id: Optional[UUID] = None
    branch_id: Optional[UUID] = None

class DepartmentCreate(DepartmentBase):
    pass
    # organization_id: UUID

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    department_head_id: Optional[UUID] = None
    branch_id: Optional[UUID] = None

class DepartmentOut(DepartmentBase):
    id: UUID
    organization_id: UUID

    class Config:
        from_attributes = True











# User Schemas
class UserCreateSchema(BaseModel):
    username: Optional[str]
    email: EmailStr
    hashed_password: Optional[str] 
    role_id: Optional[UUID]
    organization_id: Optional[UUID]
    image_path: Optional[str]
    # If image_path is a dict (for multi file uploads) or a single URL, adjust accordingly:
    # image_path: Union[str, Dict[str, str]]
    # dashboard: Optional[List["DashboardCreateSchema"]]

    # @field_validator("hashed_password")
    # def validate_password(cls, value):
    #     if len(value) < 8:
    #         raise ValueError("Password must be at least 8 characters long")
    #     return value

class UserSchema(BaseSchema):
    username: str
    email: EmailStr
    is_active: bool
    organization_id: UUID
    role_id: Optional[UUID]
    image_path: Optional[str]
    # If image_path is a dict (for multi file uploads) or a single URL, adjust accordingly:
    # image_path: Union[str, Dict[str, str]]
    # dashboard: Optional[List["DashboardCreateSchema"]]

    class Config:
        from_attributes = True

class CreateUserResponseSchema(BaseModel):
    # id: str  # return UUID as string
    message: str
    # If image_path may be a single URL (string) or multiple (dict)
    # image_path: Union[str, Dict[str, str]]
    # image_path: Optional[str]

    class Config:
        from_attributes = True
        # json_encoders = {
        #     UUID: lambda v: str(v)
        # }

class GetUserResponseSchema(BaseModel):
    user: Dict[str, Union[str, dict]]
    employee: Dict[str, Union[str, dict]]
    organization: Dict[str, Union[str, dict]]

    class Config:
        json_encoders = {
            UUID: lambda v: str(v)
        }

class UpdateUserResponseSchema(BaseModel):
    message: str
    user_id: str

    class Config:
        json_encoders = {
            UUID: lambda v: str(v)
        }

# Tenancy Schemas
class TenancyCreateSchema(BaseModel):
    organization_id: UUID
    start_date: date
    billing_cycle: Optional[str] = "Monthly"
    terms_and_conditions_id: Optional[UUID]
    terms_and_conditions: Optional[List["TermsAndConditionsCreateSchema"]]

class TenancySchema(BaseSchema):
    organization_id: UUID
    start_date: date
    end_date: Optional[date]
    billing_cycle: str
    status: str
    terms_and_conditions_id: Optional[UUID]

    # @field_validator("billing_cycle")
    # def validate_billing_cycle(cls, value):
    #     if value not in ["Monthly", "Mid-Year", "Annually"]:
    #         raise ValueError("Billing cycle must be 'Monthly' 'Mid-Year' or 'Annually'")
    #     return value
    
    class Config:
        from_attributes = True



# Terms and Conditions Schemas
class TermsAndConditionsCreateSchema(BaseModel):
    title: str
    content: Dict
    version: Optional[str]
    is_active: Optional[bool] = True


class TermsAndConditionsSchema(BaseSchema):
    title: str
    content: Dict
    version: str
    is_active: bool

    class Config:
        from_attributes = True

# Billing Schemas
class BillCreateSchema(BaseModel):
    tenancy_id: UUID
    amount: float
    due_date: date
    status: PaymentStatus

class BillSchema(BaseSchema):
    tenancy_id: UUID
    amount: float
    due_date: date
    status: PaymentStatus

    class Config:
        from_attributes = True

#Payment Schema
class PaymentCreateSchema(BaseModel):
    bill_id: UUID
    amount_paid: float
    payment_date: datetime
    payment_method: str
    transaction_id: str
    status: PaymentStatus

class PaymentSchema(BaseSchema):
    bill_id: UUID
    amount_paid: float
    payment_date: datetime
    payment_method: str
    transaction_id: str
    status: PaymentStatus

# Employee Schemas
class EmployeeCreateSchema(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    title: Optional[str] = Title.other.value
    gender: Optional[str] = Gender.other.value
    date_of_birth: Optional[date] = None
    marital_status: Optional[str] = MaritalStatus.other.value
    email: EmailStr
    contact_info: Optional[Dict] = {}
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    is_active: Optional[bool] = True
    custom_data: Optional[Dict] = {}
    profile_image_path: Optional[str] = None
    organization_id: UUID
    rank_id: Optional[UUID] = None
    department_id: Optional[UUID] = None
    last_promotion_date:Optional[date] = None
    staff_id: Optional[str] = None
    employee_type_id:Optional[UUID] = None


    @model_validator(mode="before")
    def parse_json_if_string(cls, values):
        if isinstance(values, str):
            try:
                return json.loads(values)
            except Exception as e:
                raise ValueError("Invalid JSON provided") from e
        return values

class EmployeeSchema(BaseSchema):
    first_name: str
    middle_name: Optional[str]
    last_name: str
    title: Optional[str] = Title.other.value
    gender: Optional[str] = Gender.other.value
    date_of_birth: Optional[date]
    marital_status: Optional[str] = MaritalStatus.other.value
    email: EmailStr
    # contact_info: Optional[Dict]
    contact_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    hire_date: Optional[date]
    termination_date: Optional[date]
    is_active: Optional[bool]
    # custom_data: Optional[Dict]
    custom_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    profile_image_path: Optional[str]
    organization_id: UUID
    rank_id: Optional[UUID]
    department_id: Optional[UUID]
    last_promotion_date:Optional[date]
    employee_type_id:Optional[UUID]

    # Validator for contact_info: if the incoming value is the string "{}" convert it to {}
    @field_validator("contact_info", mode="before")
    def validate_contact_info(cls, v):
        if isinstance(v, str) and v.strip() == "{}":
            return {}
        return v
    
    @field_validator("contact_info", mode="before")
    def wrap_non_dict(cls, v):
        # already a dict (or None)? leave it
        if v is None or isinstance(v, dict):
            return v
        # otherwise wrap whatever it is under a generic key
        return {"value": v}

    # Validator for custom_data: if the incoming value is the string "{}" convert it to {}
    @field_validator("custom_data", mode="before")
    def validate_custom_data(cls, v):
        if isinstance(v, str) and v.strip() == "{}":
            return {}
        return v
    
    @field_validator("custom_data", mode="before")
    def wrap_non_dict_custom(cls, v):
        if v is None or isinstance(v, dict):
            return v
        return {"value": v}


    class Config:
        from_attributes = True


class StaffOption(BaseModel):
    id: UUID
    title: str
    first_name: str
    middle_name:  Optional[str] = None
    last_name: str

    class Config:
        orm_mode = True

# Academic Qualification Schemas
class AcademicQualificationCreateSchema(BaseModel):
    employee_id: UUID
    degree: str
    institution: str
    year_obtained: int
    details: Optional[Dict] = {}
    certificate_path: Optional[str]

    @field_validator("year_obtained")
    def validate_year_obtained(cls, value):
        current_year = datetime.now().year
        if not (1900 <= value <= current_year):
            raise ValueError("Year obtained must be between 1900 and the current year")
        return value


class AcademicQualificationSchema(BaseSchema):
    employee_id: UUID
    degree: str
    institution: str
    year_obtained: int
    details: Optional[Dict]
    certificate_path: Optional[str]





# Professional Qualification Schemas
class ProfessionalQualificationCreateSchema(BaseModel):
    employee_id: UUID
    qualification_name: str
    institution: str
    year_obtained: int
    details: Optional[Dict] = {}
    license_path: Optional[str]

    @field_validator("year_obtained")
    def validate_year_obtained(cls, value):
        current_year = datetime.now().year
        if not (1900 <= value <= current_year):
            raise ValueError("Year obtained must be between 1900 and the current year")
        return value

# Professional Qualification Schemas
class ProfessionalQualificationSchema(BaseSchema):
    employee_id: UUID
    qualification_name: str
    institution: str
    year_obtained: int
    details: Optional[Dict]
    license_path: Optional[str]

# Employment History Schemas
class EmploymentHistoryCreateSchema(BaseModel):
    employee_id: UUID
    job_title: str
    company: str
    start_date: date
    end_date: Optional[date]
    details: Optional[Dict] = {}
    documents_path: Optional[str]

    @field_validator("end_date")
    def validate_end_date(cls, value, values):
        start_date = values.get("start_date")
        if value and start_date and value < start_date:
            raise ValueError("End date cannot be earlier than the start date")
        return value
    

# Employment History Schemas
class EmploymentHistorySchema(BaseSchema):
    employee_id: UUID
    job_title: str
    company: str
    start_date: date
    end_date: Optional[date]
    details: Optional[Dict]
    documents_path: Optional[str]


# Emergency Contact Schemas
class EmergencyContactCreateSchema(BaseModel):
    employee_id: UUID
    name: str
    relation: str
    phone: str
    address: Optional[str]
    details: Optional[Dict] = {}

    @field_validator("phone")
    def validate_phone(cls, value):
        if len(value) < 10 or not value.isdigit():
            raise ValueError("Phone number must be at least 10 digits and numeric")
        return value
    

class EmergencyContactSchema(BaseSchema):
    employee_id: UUID
    name: str
    relation: str
    phone: str
    address: Optional[str]
    details: Optional[Dict]


# Next of Kin Schemas
class NextOfKinCreateSchema(BaseModel):
    employee_id: UUID
    name: str
    relation: str
    phone: str
    address: Optional[str]
    details: Optional[Dict] = {}

    @field_validator("phone")
    def validate_phone(cls, value):
        if len(value) < 10 or not value.isdigit():
            raise ValueError("Phone number must be at least 10 digits and numeric")
            
        return value

    class NextOfKinSchema(BaseSchema):
        employee_id: UUID
        name: str
        relation: str
        phone: str
        address: Optional[str]
        details: Optional[Dict]



# Employment History Schemas
class EmploymentHistoryCreateSchema(BaseModel):
    employee_id: UUID
    job_title: str
    company: str
    start_date: date
    end_date: Optional[date]
    details: Optional[Dict] = {}
    documents_path: Optional[str]

    @field_validator("end_date")
    def validate_end_date(cls, value, values):
        start_date = values.get("start_date")
        if value and start_date and value < start_date:
            raise ValueError("End date cannot be earlier than the start date")
        return value

class EmploymentHistorySchema(BaseSchema):
    employee_id: UUID
    job_title: str
    company: str
    start_date: date
    end_date: Optional[date]
    details: Optional[Dict]
    documents_path: Optional[str]

# Next of Kin Schemas
class NextOfKinSchema(BaseSchema):
    employee_id: UUID
    name: str
    relation: str
    phone: str
    address: Optional[str]
    details: Optional[Dict]


# Employee Data Input Schemas
class EmployeeDataInputBase(BaseModel):
    employee_id: UUID
    organization_id: UUID
    data: Any
    request_type: str = Field(..., pattern= "^(save|update)$")
    data_type: str

class EmployeeDataInputCreate(EmployeeDataInputBase):
    pass

class EmployeeDataInputUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern= "^(Pending|Approved|Rejected)$")
    comments: Optional[str]

class EmployeeDataInputInDBBase(EmployeeDataInputBase):
    id: UUID
    request_date: datetime
    status: str
    comments: Optional[str]

    class Config:
        from_attributes = True

class EmployeeDataInput(EmployeeDataInputInDBBase):
    pass


class Attachment(BaseModel):
    filename: str
    url: str

class EmployeeDataInputRead(BaseModel):
    id: UUID
    account_name: str   = Field(..., alias="Account Name")
    role:         str
    data:         Dict[str, Any]
    attachments:  List[Attachment]    = Field(..., alias="Attachments")
    issues:       str                 = Field(..., alias="Issues")
    actions:      str                 = Field(..., alias="Actions")

    class Config:
        from_attributes = True
        # allow_population_by_field_name = True
        validate_by_name = True



# File Storage Schema
class FileStorageSchema(BaseSchema):
    file_name: str
    file_path: str
    file_type: str
    uploaded_by_id: Optional[UUID]
    record_id: UUID
    record_type: str
    organization_id: UUID

# Audit Log Schema
class AuditLogSchema(BaseSchema):
    action: str
    table_name: str
    record_id: UUID
    performed_by: Optional[UUID]
    timestamp: datetime


# System Setting Schema
class SystemSettingCreateSchema(BaseModel):
    setting_name: str
    setting_value: Dict
    organization_id: Optional[UUID] 

class SystemSettingSchema(BaseSchema):
    setting_name: str
    setting_value: Dict
    organization_id: Optional[UUID] 

    class Config:
        from_attributes = True

# Dashboard Schema
class DashboardCreateSchema(BaseModel):
    dashboard_name: str
    dashboard_data: Dict
    access_url: str
    organization_id: UUID


class DashboardSchema(BaseSchema):
    dashboard_name: str
    dashboard_data: Dict
    access_url: str
    organization_id: UUID


    class Config:
        from_attributes = True


class DataCreateBankSchema(BaseModel):
    data_name: str
    data: Union[Dict, List]  # Accepts both dictionary and list
    # organization_id: Optional[UUID] = None

    # class Config:
    #     from_attributes = True


class DataBankSchema(BaseSchema):
    data_name: str
    data:  Union[Dict, List]
    # organization_id: Optional[UUID] = None


    class Config:
        from_attributes = True




# Nested Schemas Example
class OrganizationDetailSchema(OrganizationSchema):
    users: List[UserSchema] = []
    roles: List[RoleSchema] = []
    settings: List[SystemSettingSchema] = []



# -------------------------------
# Rank Schemas
# -------------------------------
class RankBase(BaseModel):
    name: str = Field(..., description="Name of the rank (e.g., 'Junior Developer')")
    min_salary: Decimal = Field(..., description="Minimum salary for this rank")
    max_salary: Optional[Decimal] = Field(None, description="Optional maximum salary")
    currency: str = Field("GHS", description="Currency code (e.g., GHS, USD)")
    conversion_info: Optional[Dict[str, Any]] = Field(None, description="Additional currency conversion details")

class RankCreate(RankBase):
    organization_id: UUID = Field(..., description="Organization identifier")

class RankUpdate(BaseModel):
    name: Optional[str] = None
    min_salary: Optional[Decimal] = None
    max_salary: Optional[Decimal] = None
    currency: Optional[str] = None
    conversion_info: Optional[Dict[str, Any]] = None

class RankOut(RankBase):
    id: UUID
    organization_id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# -------------------------------
# PromotionPolicy Schemas
# -------------------------------
class PromotionPolicyBase(BaseModel):
    policy_name: str = Field(..., description="Name of the promotion policy")
    criteria: Dict[str, Any] = Field(..., description="JSON criteria for promotions")
    supporting_document_template: Optional[str] = Field(None, description="URL/reference for a supporting document template")
    is_active: bool = Field(True, description="Whether the policy is active")

class PromotionPolicyCreate(PromotionPolicyBase):
    organization_id: UUID = Field(..., description="Organization identifier")

class PromotionPolicyUpdate(BaseModel):
    policy_name: Optional[str] = None
    criteria: Optional[Dict[str, Any]] = None
    supporting_document_template: Optional[str] = None
    is_active: Optional[bool] = None

class PromotionPolicyOut(PromotionPolicyBase):
    id: UUID
    organization_id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# -------------------------------
# PaymentGatewayConfig Schemas
# -------------------------------
class PaymentGatewayConfigBase(BaseModel):
    provider_name: str = Field(..., description="Payment provider name")
    api_key: str = Field(..., description="API key")
    api_url: str = Field(..., description="API endpoint URL")
    additional_config: Optional[Dict[str, Any]] = Field(None, description="Any additional configuration details")

class PaymentGatewayConfigCreate(PaymentGatewayConfigBase):
    organization_id: UUID = Field(..., description="Organization identifier")

class PaymentGatewayConfigUpdate(BaseModel):
    provider_name: Optional[str] = None
    api_key: Optional[str] = None
    api_url: Optional[str] = None
    additional_config: Optional[Dict[str, Any]] = None

class PaymentGatewayConfigOut(PaymentGatewayConfigBase):
    id: UUID
    organization_id: UUID

    class Config:
        from_attributes = True

# -------------------------------
# Notification Schemas
# -------------------------------
class NotificationBase(BaseModel):
    type: str = Field(..., description="Notification type (e.g., 'promotion_due', 'birthday')")
    message: str = Field(..., description="Notification message")
    is_read: bool = Field(False, description="Read status")

class NotificationCreate(NotificationBase):
    organization_id: UUID = Field(..., description="Organization identifier")
    user_id: Optional[UUID] = Field(None, description="Optional target user ID")
    employee_id: Optional[UUID] = Field(None, description="Optional employee ID for individual notifications")

class NotificationUpdate(BaseModel):
    type: Optional[str] = None
    message: Optional[str] = None
    is_read: Optional[bool] = None
    user_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None

class NotificationOut(NotificationBase):
    id: UUID
    organization_id: UUID
    user_id: Optional[UUID]
    employee_id: Optional[UUID]
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# -------------------------------
# PromotionRequest Schemas
# -------------------------------
class PromotionRequestBase(BaseModel):
    employee_id: UUID = Field(..., description="Employee submitting the request")
    current_rank_id: Optional[UUID] = Field(None, description="Current rank of the employee")
    proposed_rank_id: Optional[UUID] = Field(None, description="Proposed new rank")
    promotion_effective_date: Optional[datetime] = Field(None, description="Effective date of the promotion")
    evidence_documents: Optional[List[str]] = Field(None, description="List of URLs for supporting evidence documents")
    comments: Optional[str] = Field(None, description="Comments regarding the promotion request")
    department_approved: bool = Field(False, description="Department head approval status")
    hr_approved: bool = Field(False, description="HR approval status")

class PromotionRequestCreate(PromotionRequestBase):
    pass

class PromotionRequestUpdate(BaseModel):
    proposed_rank_id: Optional[UUID] = None
    promotion_effective_date: Optional[datetime] = None
    evidence_documents: Optional[List[str]] = None
    comments: Optional[str] = None
    department_approved: Optional[bool] = None
    department_approval_date: Optional[datetime] = None
    hr_approved: Optional[bool] = None
    hr_approval_date: Optional[datetime] = None

class PromotionRequestOut(PromotionRequestBase):
    id: UUID
    request_date: datetime
    department_approval_date: Optional[datetime] = None
    hr_approval_date: Optional[datetime] = None

    class Config:
        from_attributes = True

# -------------------------------
# EmployeePaymentDetail Schemas
# -------------------------------
class EmployeePaymentDetailBase(BaseModel):
    employee_id: UUID = Field(..., description="Employee identifier")
    payment_mode: str = Field(..., description="Payment mode (e.g., 'Bank Transfer', 'MTN MOMO')")
    bank_name: Optional[str] = Field(None, description="Bank name (if applicable)")
    account_number: Optional[str] = Field(None, description="Account number (if applicable)")
    mobile_money_provider: Optional[str] = Field(None, description="Mobile money provider (if applicable)")
    wallet_number: Optional[str] = Field(None, description="Wallet number (if applicable)")
    additional_info: Optional[Dict[str, Any]] = Field(None, description="Any extra details")
    is_verified: bool = Field(False, description="Verification status")

class EmployeePaymentDetailCreate(EmployeePaymentDetailBase):
    pass

class EmployeePaymentDetailUpdate(BaseModel):
    payment_mode: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    mobile_money_provider: Optional[str] = None
    wallet_number: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    is_verified: Optional[bool] = None

class EmployeePaymentDetailOut(EmployeePaymentDetailBase):
    id: UUID

    class Config:
        from_attributes = True

# -------------------------------
# SalaryPayment Schemas
# -------------------------------
class SalaryPaymentBase(BaseModel):
    employee_id: UUID = Field(..., description="Employee identifier")
    rank_id: Optional[UUID] = Field(None, description="Associated rank identifier")
    amount: Decimal = Field(..., description="Salary amount")
    currency: str = Field("USD", description="Currency code")
    payment_method: str = Field(..., description="Method of payment (e.g., 'Bank Transfer')")
    transaction_id: str = Field(..., description="Unique transaction identifier")
    status: str = Field("Success", description="Payment status (e.g., 'Success', 'Failed')")

class SalaryPaymentCreate(SalaryPaymentBase):
    pass

class SalaryPaymentUpdate(BaseModel):
    rank_id: Optional[UUID] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    transaction_id: Optional[str] = None
    status: Optional[str] = None

class SalaryPaymentOut(SalaryPaymentBase):
    id: UUID
    payment_date: datetime

    class Config:
        from_attributes = True


class DashboardBaseSchema(BaseModel):
    dashboard_name: str = Field(..., description="Name of the dashboard view")
    dashboard_data: Dict[str, Any] = Field(
        ..., description="Configuration data for the dashboard (JSON)"
    )
    access_url: str = Field(..., description="Accessible URL for this dashboard")

class DashboardCreateSchema(DashboardBaseSchema):
    organization_id: UUID = Field(..., description="The organization this dashboard belongs to")
    user_id: Optional[UUID] = Field(None, description="Owner user id (optional)")


class DashboardUpdateSchema(BaseModel):
    dashboard_name: Optional[str] = Field(None, description="Name of the dashboard view")
    dashboard_data: Optional[Dict[str, Any]] = Field(None, description="Configuration data for the dashboard (JSON)")
    access_url: Optional[str] = Field(None, description="Accessible URL for this dashboard")
    # Generally, organization and user are not updatable via dashboard update API.
    
    class Config:
        from_attributes = True
        
class DashboardSchema(DashboardBaseSchema):
    # id: UUID
    organization_id: UUID
    user_id: Optional[UUID]

    class Config:
        from_attributes = True


# ---------------------------------
# Summary endpoint schemas
# ---------------------------------
class SummaryCounts(BaseModel):
    branches: Optional[int] = 0
    departments: Optional[int] = 0
    ranks: Optional[int] = 0
    roles: int
    users: int
    employees: int
    promotion_policies: Optional[int] = 0
    tenancies: Optional[int] = 0
    bills: Optional[int] = 0
    payments: Optional[int] = 0

    class Config:
        from_attributes = True

class OrganizationSummarySchema(BaseModel):
    organization: OrganizationSchema
    counts: SummaryCounts

    class Config:
        from_attributes = True

class OrganizationCountSummarySchema(BaseModel):
    counts: SummaryCounts

    class Config:
        from_attributes = True
    

class EmployeeUserUpdateResponse(BaseModel):
    employee_id: str
    staffId:      Optional[str] = None
    name:         Optional[str] = None
    department:   Optional[dict]  # {"id": <str>, "name": <str>, "branch_id": <str>}
    branch:       Optional[dict]  # {"id": <str>, "name": <str>, "location": <str>}
    role:         Optional[dict]  # {"id": <str>, "name": <str>}

    class Config:
        # Ensure UUIDs serialize as strings
        json_encoders = { UUID: lambda v: str(v) }


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# --- SCHEMAS ---------------------------------------------------------------

class TourCompletedResponse(BaseModel):
    tourCompleted: bool = Field(..., description="Has the user completed the tour?")

class TourCompletedUpdate(BaseModel):
    tourCompleted: bool = Field(..., description="Set to true once tour is done, false to reset")


# ---------- Pydantic Settings Models ----------
class TenantEmailSettings(BaseModel):
    provider: str #"smtp" | "sendgrid"
    host: Optional[str]
    port: Optional[int]
    username: Optional[str]
    password: Optional[str]
    use_tls: bool = True
    api_key: Optional[str]
    default_from: EmailStr
    templates_dir: str = "templates/emails"
    logo_path: Optional[str] = None
    schema_based: bool = False  # True for App1, False for App2

    @root_validator(pre=True)
    def normalize_sendgrid(cls, values):
        if values.get("host") == "smtp.sendgrid.net":
            values["username"] = "apikey"  # SendGrid expects "apikey" as username
        return values
    
    class Config:
        schema_extra = {
            "example": {
                "provider": "smtp",
                "host": "smtp.mail.yahoo.com",
                "port": 465 | 587 ,
                "username": "sammy@yahoo.com",
                "password": "app-password-here",
                "use_tls": True,
                "api_key": "",
                "default_from": "sammy@yahoo.com",
                "templates_dir": "templates/emails",
                "logo_path": "https://path/to/logo.png",
                "schema_based": True
            }
        }


# class EmailConfigCreate(BaseModel):
#     provider: str
#     host: Optional[str]
#     port: Optional[int]
#     username: Optional[str]
#     password: Optional[str]
#     use_tls: bool = True
#     api_key: Optional[str]
#     default_from: EmailStr
#     templates_dir: Optional[str] = "templates/emails"
#     logo_path: Optional[str]

#     @root_validator(pre=True)
#     def normalize_provider(cls, values):
#         if not values.get('provider') and values.get('host'):
#             host = values['host'].lower()
#             if 'smtp' in host:
#                 values['provider'] = 'smtp'
#             elif 'sendgrid' in host:
#                 values['provider'] = 'sendgrid'
#         return values

class EmailConfigCreate(TenantEmailSettings):
    pass


class EmailConfigRead(EmailConfigCreate):
    id: str = Field(..., description="Organization UUID")

class EmailConfigUpdate(BaseModel):
    provider: Optional[str]
    host: Optional[str]
    port: Optional[int]
    username: Optional[str]
    password: Optional[str]
    use_tls: Optional[bool]
    api_key: Optional[str]
    default_from: Optional[EmailStr]
    templates_dir: Optional[str]
    logo_path: Optional[str]

    


class EmailSendRequest(BaseModel):
    to: List[EmailStr] = Field(..., description="One or more recipient email addresses")
    subject: str = Field(..., description="Email subject line")
    template_name: str = Field(..., description="Name of the Jinja2 HTML template file")
    context: Dict[str, Any] = Field(default_factory=dict, description="Context variables to render into the template")