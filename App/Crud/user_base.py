import asyncio
import json
import random
import string
from fastapi import HTTPException, Depends, BackgroundTasks, UploadFile, HTTPException
from fastapi.responses import FileResponse
import requests
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from typing import Optional, Dict, List
from uuid import UUID
from passlib.context import CryptContext
import secrets
from pydantic import EmailStr
from smtplib import SMTPException
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import logging
from jinja2 import Template
import pandas as pd
import io

import urllib.parse

from Apis.summary import push_summary_update
from Service.sms_service import BaseSMSService
from Service.storage_service import BaseStorage
from Utils.sms_utils import get_sms_service
from Utils.storage_utils import get_storage_service
from Models.Tenants.organization import (Branch, Organization, Rank)
from Models.dynamic_models import EmployeeDynamicData, BulkUploadError
from Models.models import (Employee, User, Department, EmployeePaymentDetail,
                           AcademicQualification, EmergencyContact, EmployeeType,
                           EmploymentHistory, ProfessionalQualification, NextOfKin,
                           SalaryPayment)
from Utils.rate_limiter import RateLimiter
from Schemas.schemas import OrganizationCreateSchema, EmployeeCreateSchema
from Models.Tenants.role import Role
import os
from datetime import datetime, date, timedelta
import re
from Crud.adv import RoleCache
from Utils.util import Validator, get_organization_acronym, extract_items
from Utils.config import BaseConfig, DevelopmentConfig, get_config
from Utils.security import Security
import aiohttp
from Service.gcs_service import GoogleCloudStorage
from Service.email_service import EmailService, get_email_template, get_update_notification_email_template
from aiohttp import ClientTimeout, FormData
from rapidfuzz import process, fuzz


rate_limiter = RateLimiter(max_attempts=5, period=60)  # 5 attempts per 60 seconds

settings = get_config()




# Initialize the global Security instance.
# In a multi-tenant system sharing one schema, a common secret key is often used.
global_security = Security(secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM, token_expire_minutes=60)


# from fastapi import HTTPException, UploadFile, BackgroundTasks
# from sqlalchemy.orm import Session
# from uuid import UUID
# from typing import Optional, Dict
# import json
# import requests
# import aiohttp

# from utils.security import generate_random_string, hash_password
# from utils.cloud_storage import GoogleCloudStorage
# from utils.email_service import EmailService
# from models import User, Employee, Role
# from settings import FACIAL_AUTH_API_URL, BUCKET_NAME



# Configure Logger
# LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants for Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Secure Email Configuration
# SMTP_CREDENTIALS = {
#     "sender_email": os.getenv("SMTP_SENDER_EMAIL"),
#     "sender_password": os.getenv("SMTP_SENDER_PASSWORD"),
#     "smtp_host": os.getenv("SMTP_HOST"),
#     "smtp_port": int(os.getenv("SMTP_PORT", 587)),
# }



# # Default Permissions for Roles
# DEFAULT_PERMISSIONS = {
#     "staff": {"create_task": True, "view_task": True, "update_task": False, "delete_task": False},
#     "manager": {"create_task": True, "view_task": True, "update_task": True, "delete_task": False},
# }

# Constants for Random Username and Password Generation
CHARACTER_SET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()"
USERNAME_LENGTH = 8
PASSWORD_LENGTH = 12

# Helper function to generate random string
def generate_random_string(length: int) -> str:
    return ''.join(secrets.choice(CHARACTER_SET) for _ in range(length))


# Audit Logging
async def log_audit(db: AsyncSession, audit_model, action: str, performed_by: UUID, table_name: str, record_id: Optional[UUID]):
    """
    Logs an audit entry in the database.
    """
    audit_entry = audit_model(
        action=action,
        performed_by=performed_by,
        table_name=table_name,
        record_id=record_id,
    )
    db.add(audit_entry)
    await db.commit()


# Permissions Retrieval from Database
def get_permissions_from_db(db: AsyncSession, role_name: str) -> Dict[str, bool]:
    """
    Fetch role permissions dynamically from the database.
    """
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"Role {role_name} not found.")
    return role.permissions



# Validation for Uploaded File
def validate_file_structure(data: pd.DataFrame, required_columns: List[str]):
    for column in required_columns:
        if column not in data.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required column: {column}"
            )

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# 1) Additional synonyms if your file calls it "date_of_b"
DATE_SYNONYMS = {
    "date_of_b": "date_of_birth",
    "dob": "date_of_birth",
    "birth_date": "date_of_birth",
    "birth": "date_of_birth",
    "Date of Birth": "date_of_birth",
    "DOB": "date_of_birth",
    "Birth Date": "date_of_birth",
    "Birth": "date_of_birth",
    "date_of_birth": "date_of_birth",
    "Hire Date": "hire_date",
    "Hire": "hire_date",
    "hire_date": "hire_date",
    "hire_date": "hire date",
    "start_date": "start date",
    "start_date": "start_date",
    "Termination Date": "termination_date",
    "Termination": "termination_date",
    "termination_date": "termination_date",
    "end_date": "end date",
    "end_date": "end_date",
    "termination_date": "exit date",
    "termination_date": "exit_date",
    "termination_date": "last day",
    "termination_date": "last_day",
    "termination_date": "termination date"

    # etc...
}


# --------------------------
# Mapping Definitions
# --------------------------
# Expected field names (all lowercase) for various models.
model_field_map: Dict[str, set] = {
    "employee": {"first_name", "middle_name", "last_name", "title", "gender", "date_of_birth",
                 "marital_status", "email", "contact_info", "hire_date", "termination_date",
                 "profile_image_path", "staff_id", "last_promotion_date", "employee_type_id",
                 "department_id", "rank_id", "department", "rank", "employee type", "employment type",
                 "role", "salary"},
    "academic_qualification": {"degree", "institution", "year_obtained", "details", "certificate_path"},
    "professional_qualification": {"qualification_name", "institution", "year_obtained", "details", "license_path"},
    "employment_history": {"job_title", "company", "start_date", "end_date", "details", "documents_path"},
    "emergency_contact": {"name", "relation", "emergency_phone", "emergency_address", "details"},
    "next_of_kin": {"name", "relation", "nok_phone", "nok_address", "details"},
    "salary_payment": {"amount", "currency", "payment_date", "payment_method", "transaction_id", "status", "approved_by"},
    "employee_payment_detail": {"payment_mode", "bank_name", "account_number", "mobile_money_provider", "wallet_number", "additional_info", "is_verified"},
    "employee_type": {"type_code", "description", "default_criteria"},
    "department": {"name", "department_head_id", "branch_id"},
    "rank": {"name", "min_salary", "max_salary", "currency"},
    # "branch": {"name", "location", "manager_id"},
    # "role": {"name", "permissions"},
}

# Mapping from model names to model classes.
model_classes = {
    "employee": Employee,
    "academic_qualification": AcademicQualification,
    "professional_qualification": ProfessionalQualification,
    "employment_history": EmploymentHistory,
    "emergency_contact": EmergencyContact,
    "next_of_kin": NextOfKin,
    "salary_payment": SalaryPayment,
    "employee_payment_detail": EmployeePaymentDetail,
    "employee_type": EmployeeType,
    "department": Department,
    "rank": Rank,
    # "branch": None,  # Handled separately via process_related_field
    # "role": None,  # Handled separately via process_related_field
}

# ------------------------------------------------------------------------------
# 1. Column Synonyms
# ------------------------------------------------------------------------------
# We define synonyms for each concept. Example:
SYNONYMS_MAP = {
    "first_name": {"first_name", "first", "fname", "first name", "firstname", "Given Name", "Given Name (First Name)", "given name", "givenname"},
    "middle_name": {"middle_name", "middle", "mname", "middle name", "middlename", "Middle Name", "Middle Name (Middle Name)", "middle name"},
    "last_name": {"last_name", "last", "lname", "last name", "lastname", "Family Name", "Surname", "Surname (Family Name)", "surname", "family name", "familyname"},
    "title": {"title", "salutation", "prefix", "name prefix", "name prefix (title)", "name prefix (salutation)", "name prefix (prefix)"},
    "staff_id":{"id", "staff id", "staff_id"},
    "profile_image_path": {"profile image", "image", "picture", "profile", "profile picture", "profile pic", "pic"},
    "department": {"department", "dept", "division", "section", "unit", "department name", "department name (dept)", "department name (division)", "department name (section)", "department name (unit)"},
    "role": {"role", "job role", "job", "position","job function", "post", "system role", "designation", "job description", "job title", "job title (role)", "job role (role)", "job role (job)", "job title (job)", "job description (role)", "job description (job)", "job title (job title)", "job role (job role)", "job description (job description)"},
    "rank": {"rank", "grade", "level", "job level", "job grade", "job level (grade)", "job grade (level)", "job grade (grade)", "job level (level)"},
    "employee_type": {"employee type", "employment type", "emp type", "type of employment", "type", "employment type (type)", "employment type (employee type)", "employment type (employment type)", "employment type (emp type)", "employment type (type of employment)"},
    "branch": {"branch", "location", "site", "office", "workplace", "branch name", "branch location", "branch location (site)", "branch location (office)", "branch location (workplace)", "office location", "office location (site)", "office location (branch)", "office location (workplace)", "workplace location", "workplace location (site)", "workplace location (branch)", "workplace location (office)"},
    # For academic qualifications:
    "degree": {"degree", "Academic_Degree", "Academic Degree", "academic_qualification", "academic qualification", "Highest Degree", "Highest Degree (Academic Degree)", "Highest Degree (qualification)", "Highest Degree (Highest Degree)"},
    "institution": {"institution", "school", "university", "college", "Academic_Institution", "Academic Institution", "school name", "school name (institution)", "school name (school)", "school name (university)", "school name (college)", "school name (Academic Institution)", "school name (Academic_Institution)", "Certification Institution", },
    # For professional qualifications:
    "qualification_name": {"qualification_name", "Professional Certification", "professional_qualification", "professional qualification", "Certification Name", "Certification Name (qualification_name)", "Certification Name (Professional Certification)", "Certification Name (professional_qualification)"},
    #For graduation year for both academic and professional qualifications
    "year_obtained": {"year_obtained", "year", "graduation year", "years_of_experience", "year_of_experience" , "graduation date (year)", "graduation_date (graduation year)", "graduation year (graduation year)", "year obtained", "year obtained (year)", "year obtained (graduation year)", "year obtained (graduation year)"},
    # For employment history:
    "job_title": {"job_title", "job title", "position", "designation"},
    "start_date": {"start_date"},
    "end_date": {"end_date"},
    # For emergency contacts and next of kin, "name" is already generic.
    "name": {"name", "full name", "Full Name"},
    "relation": {"relation", "relationship", "kinship", "relation to employee", "relationship to employee"},
    "emergency_address": {"emergency_address", "emergency_location", "emergency address","emergency_residence", "emergency home address", "emergency contact address", "emergency address (location)", "emergency address (residence)", "emergency address (home address)", "emergency address (contact address)"},
    "emergency_phone": {"emergency_phone", "emergency phone","emergency_contact_number", "emergency_mobile", "emergency_cell", "emergency_telephone", "emergency phone number", "emergency contact number", "emergency mobile number", "emergency cell number", "emergency telephone number"},
    "company": {"company", "employer", "organization", "company name", "employer name", "organization name"},
    # For NextOfKin and EmergencyContact:
    "nok_phone": {"nok_phone", "nok_contact_number", "nok address","nok_mobile", "nok_cell", "nok_telephone"},
    "nok_address": {"nok_address", "nok address","nok_location", "nok_residence", "nok home address", "nok contact address", "nok address (location)", "nok address (residence)", "nok address (home address)", "nok address (contact address)"},
    # For payment details:
    "payment_mode": {"payment_mode","mode", "method", "payment_method","payment method"},
    "bank_name": {"bank_name", "bank name"  ,"name of bank", "bank", "name_of_bank"},
    "account_number": {"account_number", "account number", "account", "account #", "acc", "acc #"},
    "mobile_money_provider":{"mobile_money_provider", "mobile money provider", "momo provider", "momo_provider", "provider"},
    "wallet_number": {"wallet_number", "wallet number", "wallet #", "wallet", "momo number", "momo_number", "momo #"},
    
}



# --- Helper: Normalize Column Name ---
def normalize_column_name(col_name: str) -> str:
    """
    Lowercase, trim, and remove non-alphanumeric characters (except space).
    """
    col_name = col_name.strip().lower()
    col_name = re.sub(r'[^a-z0-9\s]', '', col_name)
    col_name = re.sub(r'\s+', ' ', col_name)
    return col_name

# --- Helper: Get Flat List of Synonyms ---
def get_flat_synonyms():
    flat = []
    for synonyms in SYNONYMS_MAP.values():
        for s in synonyms:
            flat.append(normalize_column_name(s))
    
    # print("flat: ", flat)
    return flat

FLAT_SYNONYMS = get_flat_synonyms()

# --- Helper: Fuzzy Matching for Column Names ---
def find_standard_concept(col_name: str, threshold: int = 85) -> str:
    """
    Normalize the given column name and return a canonical concept.
    Steps:
      1. Normalize the name.
      2. Check DATE_SYNONYMS.
      3. Fuzzy-match using RapidFuzz against our flat synonyms.
      4. As fallback, if the normalized name exactly matches an expected employee field, use that.
    """
    norm = normalize_column_name(col_name)
    if norm in DATE_SYNONYMS:
        return DATE_SYNONYMS[norm]
    best, score, _ = process.extractOne(norm, FLAT_SYNONYMS, scorer=fuzz.ratio)
    if best and score >= threshold:
        for concept, synonyms in SYNONYMS_MAP.items():
            norm_syns = {normalize_column_name(s) for s in synonyms}
            if best in norm_syns:
                return concept
    for field in model_field_map["employee"]:
        if normalize_column_name(field) == norm:
            # print("\n\nreturned stanadardized flattened column name: ", field)
            return field
    # print("\n\nreturned stanadardized normalized column name: ", norm)
    return norm


# ------------------------------------------------------------------------------
# 2. Convert Excel Numeric Date to Python date
# ------------------------------------------------------------------------------
def excel_date_to_datetime(excel_date: float):
    """Convert an Excel float date to a Python date, if possible."""
    # Excel "serial" date starts at 1899-12-30
    try:
        base_date = datetime(1899, 12, 30)
        delta = timedelta(days=float(excel_date))
        return (base_date + delta).date()
    except:
        return excel_date


def excel_date_to_date(value) -> date:
    """
    Convert an Excel serial date (either numeric or a string that represents a number)
    to a Python date object.
    Excel serial dates start at 1899-12-30.
    """
    try:
        # If value is numeric or a numeric string, convert to float
        numeric_value = float(value)
        base_date = datetime(1899, 12, 30)
        dt = base_date + timedelta(days=numeric_value)
        return dt.date()
    except Exception:
        # If conversion fails, return the original value
        return value

def parse_date_value(value):
    """
    Attempt to convert a value to a Python date.
    - If value is numeric (or a numeric string), treat it as an Excel serial date.
    - If value is a string containing '/', assume "mm/dd/yyyy" format.
    - If value is already in "yyyy-mm-dd" or a date/datetime object, convert as needed.
    Otherwise, return the original value.
    """
    try:
        # If already a date/datetime, return the date.
        if isinstance(value, (datetime, date)):
            return value if isinstance(value, date) else value.date()
        
        # If already date/datetime, just return
        if isinstance(value, (date, datetime)):
            return value if isinstance(value, date) else value.date()
        
        # Try converting a numeric value or numeric string (Excel serial)
        try:
            numeric_val = float(value)
            # Excel serial dates start at 1899-12-30 (with Excel's leap-year bug handled implicitly)
            base_date = datetime(1899, 12, 30)
            dt = base_date + timedelta(days=numeric_val)
            return dt.date()
        except Exception:
            pass
        
        # If value contains '/', assume "mm/dd/yyyy"
        if isinstance(value, str) and "/" in value:
            try:
                dt = datetime.strptime(value.strip(), "%m/%d/%Y")
                return dt.date()
            except Exception:
                pass
        
        # Otherwise, if value contains '-', assume "yyyy-mm-dd"
        if isinstance(value, str) and "-" in value:
            try:
                dt = datetime.strptime(value.strip(), "%Y-%m-%d")
                return dt.date()
            except Exception:
                pass
    except Exception:
        pass
    return value
# ------------------------------------------------------------------------------
# 3. Sanitize row data (replace NaN with None)
# ------------------------------------------------------------------------------
def sanitize_value(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value

def sanitize_row_data(row_data: dict) -> dict:
    sanitized = {}
    for key, value in row_data.items():
        if isinstance(value, dict):
            sanitized[key] = sanitize_row_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_row_data(item) if isinstance(item, dict) else sanitize_value(item) 
                for item in value
            ]
        else:
            sanitized[key] = sanitize_value(value)
    return sanitized



# -----------------------------------------------------------------------------
# Field Synonyms Mapping
# -----------------------------------------------------------------------------
# This mapping converts UI-provided keys (which may be labels in lowercase)
# into the canonical field names used in the Employee model.
FIELD_SYNONYMS = {
    "first name": "first_name",
    "firstname": "first_name",
    "firstName": "first_name",
    "given name": "first_name",
    "givenname": "first_name",
    "middle name": "middle_name",
    "middlename": "middle_name",
    "last name": "last_name",
    "lastname": "last_name",
    "surname": "last_name",
    "title": "title",
    "name prefix": "title",  # e.g. Mr., Ms., Dr.
    "name prefix (title)": "title",
    "name prefix (salutation)": "title",  # e.g. Mr., Ms., Dr.
    "prefix": "title",  # e.g. Mr., Ms., Dr.
    "salutation": "title",  # e.g. Mr., Ms., Dr.
    "sex": "gender",
    "gender": "gender",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
    "birth date": "date_of_birth",
    "birth": "date_of_birth",
    "date of_b": "date_of_birth",  # e.g. in case the file calls it date_of_b
    "DoB": "date_of_birth",
    "marital status": "marital_status",
    "email": "email",
    "email address": "email",
    "contact info": "contact_info",
    "contact information": "contact_info",
    "contact details": "contact_info",
    "contact number": "contact_info",
    "contact phone": "contact_info",
    "contact mobile": "contact_info",
    "contact home address": "contact_info",
    "contact residential address": "contact_info",
    "contact address": "contact_info",
    "address": "contact_info",
    "phone number": "contact_info",
    "contact": "contact_info",
    "phone": "contact_info",
    "mobile": "contact_info",
    "home address": "contact_info",
    "residential address": "contact_info",
    "profile image":"profile_image_path",
    "employee image": "profile_image_path",
    "profile picture": "profile_image_path",
    "profile pic": "profile_image_path",
    "profile_image": "profile_image_path",
    "profile_image_path": "profile_image_path",
    "employee profile image": "profile_image_path",
    "employee profile picture": "profile_image_path",
    "employee profile pic": "profile_image_path",
    "employee profile_image": "profile_image_path",
    "employee profile_image_path": "profile_image_path",
    "last promotion date": "last_promotion_date",
    "hire date": "hire_date",
    "termination date": "termination_date",
    "employee type": "employee_type",  # For mapping to the EmployeeType table.
    "rank": "rank",  # For mapping to the Rank table.
    "assigned_dept": "department",  # For mapping to the Department table.
    "assigned department": "department",  # For mapping to the Department table.
    "assigned_department": "department",  # For mapping to the Department table.
    "department": "department",  # For mapping to the Department table, i.e. in the case where the manager assigns this new employee to a department or as the head_of_department.
    "branch": "branch",  # For mapping to the Branch table, i.e. in the case where the manager assigns this new employee as the branch manager.
    "staff id": "staff_id", # staff_id should be unique for each employee
    "staffid": "staff_id",
    "staff_id": "staff_id",
    "id": "staff_id",
    "employee id": "staff_id",
    "employee_id": "staff_id",


    # Any extra fields not in the list will remain as-is and later go into custom_data.
}

# -----------------------------------------------------------------------------
# Related Model Mapping
# -----------------------------------------------------------------------------
# This mapping defines keys for related collections sent from the UI.
# For example, if the UI sends an "academic_qualifications" key with a list
# of academic entries, they will be mapped to the AcademicQualification model.
RELATED_MODEL_MAP = {
    "academic_qualifications": (
        AcademicQualification,
        {"degree", "institution", "year_obtained", "details", "certificate_path"}
    ),
    "professional_qualifications": (
        ProfessionalQualification,
        {"qualification_name", "institution", "year_obtained", "details", "license_path"}
    ),
    "payment_details": (
        EmployeePaymentDetail,
        {"payment_mode", "bank_name", "account_number", "mobile_money_provider", "wallet_number", "additional_info", "is_verified"}
    ),
    "employment_history": (
        EmploymentHistory,
        {"job_title", "company", "start_date", "end_date", "details", "documents_path"}
    ),
    "emergency_contacts": (
        EmergencyContact,
        {"name", "relation", "emergency_phone", "emergency_address", "details"}
    ),
    "next_of_kins": (
        NextOfKin,
        {"name", "relation", "nok_phone", "nok_address", "details"}
    ),
    "salary_payments": (
        SalaryPayment,
        {"amount", "currency", "payment_date", "payment_method", "transaction_id", "status", "approved_by"}
    ),
    # Add more related mappings as needed.
}

# -----------------------------------------------------------------------------
# Helper: Map Fields Using Synonyms
# -----------------------------------------------------------------------------
def map_employee_fields(data: dict) -> dict:
    """
    Convert UI field keys (which may be synonyms) to canonical Employee model keys.
    """
    mapped = {}
    for key, value in data.items():
        # Normalize key to lower case and strip whitespace.
        normalized_key = key.lower().strip()
        canonical = FIELD_SYNONYMS.get(normalized_key, key)  # use synonym if available
        mapped[canonical] = value
    return mapped

# CRUD Functions for User Creation
class UserCRUD:
    def __init__(self, user_model, role_model, org_model, employee_model, audit_model):
        self.user_model = user_model
        self.role_model = role_model
        self.org_model = org_model
        self.employee_model = employee_model
        self.audit_model = audit_model
        self.role_cache = RoleCache()
    


    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def log_audit(
        self,
        # db: AsyncSession,
        db: Session,
        action: str,
        performed_by: Optional[UUID],
        table_name: str,
        record_id: Optional[UUID],
    ):
        audit_entry = self.audit_model(
            action=action,
            performed_by=performed_by,
            table_name=table_name,
            record_id=record_id,
        )
        db.add(audit_entry)
        # await db.commit()  if not None else db.commit()
        db.commit()
    
    
    
    def extract_url(self, data_str):

        # Given string
        # data_str = '{"download (4).jpeg": "https://storage.googleapis.com/developers-bucket/test-app/organizations/Ghana-India Kofi Annan Centre of Excellence in ICT/user_profiles/download (4).jpeg"}'

        # Regular expression to find a URL
        # match = re.search(r'https?://[^\s"}]+', data_str)

        try:
            # Regular expression to match a complete URL inside quotes
            match = re.search(r'https?://.*?(?=["}])', data_str)

            # Extract URL if found
            url = match.group(0) if match else None

            print(url)
            return url
        except Exception as e:
            print("url extraction error: ", e)


    def get(
        self, db: Session, identifier: str, organization_id: str
    ):
        """
        Retrieve a single record by its ID.

        :param db: Database session
        :param id: Record ID
        :return: Single record or None
        """
        try:

              # Attempt to convert the identifier to a UUID.
            try:
                user_uuid = UUID(identifier)
                is_uuid = True
            except ValueError:
                is_uuid = False
            
            # Query user by ID or Email
            if is_uuid:
                user = db.query(User).filter(
                    (User.id == user_uuid) | (User.email == identifier),
                    User.organization_id == organization_id
                ).first()
            else:
                user = db.query(User).filter(
                (User.email == identifier),
                User.organization_id == organization_id
            ).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Query related employee using user's email
            employee = db.query(Employee).filter(
                Employee.email == user.email,
                Employee.organization_id == organization_id
            ).first()

            #role data
            role = db.query(Role).filter(
                Role.id==user.role_id,
                Role.organization_id == user.organization_id
            ).first()

            org = db.query(Organization).filter(
                Organization.id== user.organization_id
            ).first()

            print("profile_iamge_path: ", employee.profile_image_path)
            if employee.profile_image_path:
                if isinstance(employee.profile_image_path, dict):
                    print("herer")
                    indx = self.extract_url(employee.profile_image_path)
                    gcs = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME)
                    decoded_file_path = urllib.parse.unquote(indx)
                    image = gcs.download_from_gcs(decoded_file_path, show_image=True)
                else:
                    indx = self.extract_url({employee.profile_image_path})
                    print("her: ", indx)
                    try:
                        gcs = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME)
                        decoded_file_path = urllib.parse.unquote(indx)
                        image = gcs.download_from_gcs(decoded_file_path, show_image=True)
                    except Exception as r:
                        print("err: ", r)

            elif not employee.profile_image_path:
                indx = "https://"


            print(f""" 
                    username email: {user.email}
                    "role": {role.name}
                    employee email: {employee.email}\n=======================================================================\n
                    profile image: {indx}
                    organization: {org.name}
                 """)

            data =  {
                "user": {
                    "user_id": user.id,
                    "Role":role.name,
                    "Permissions": role.permissions 
                    # "id": user.id,
                    # "email": user.email,
                    # "organization_id": user.organization_id,
                    # Add other user fields if needed
                },
                "employee": {
                    "id":employee.id,
                    "title": employee.title,
                    "first_name": employee.first_name,
                    "middle_name": employee.middle_name,
                    "last_name":employee.last_name,
                    "gender":employee.gender,
                    "email": employee.email if employee else None,
                    "organization": org.name,
                    "contact_info": employee.contact_info,
                    "custom_data": employee.custom_data,
                    "profile_image": "" if not indx else indx
                    # Add other employee fields if needed
                }, 
                # "image": image
            }

            return data
            # return image
            # return  {
                # "data": data,
            # return    FileResponse(image, media_type="image/jpeg", filename=os.path.basename(indx)) 

            # }

        except Exception as e:
            print("error occurred",e)
            raise HTTPException(status_code=500, detail=f"error occurred with message:\n {str(e)}")

    
    def enroll_user_for_facial_auth(self, username: str, image: UploadFile):
        """
        Send the user image directly to the facial authentication API.
        """
        try:
            response = requests.post(
                f"{settings.FACIAL_AUTH_API_URL}/users/create",
                data={"username": username},
                files={"file": (image.filename, image.file.read())},
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Facial authentication enrollment failed: {str(e)}")
    

        # --------------------------
    # Helper: Process Related Field
    # --------------------------
    def process_related_field(self, db: Session, background_tasks: BackgroundTasks, organization_id: str, value: str, table, lookup_field: str, defaults: dict) -> str:
        """
        Query the given table (e.g. Department, Rank, EmployeeType, Role) for a record matching `value`
        (case-insensitive). If not found, create a new record with provided defaults.
        Return the record's id as a string.
        """
        value = value.strip()
        obj = db.query(table).filter(
            getattr(table, lookup_field).ilike(value),
            table.organization_id == organization_id
        ).first()
        if not obj:
            data = {lookup_field: value, "organization_id": organization_id}
            data.update(defaults)
            obj = table(**data)
            db.add(obj)
            db.commit()
            db.refresh(obj)
        
            background_tasks.add_task(push_summary_update, db, str(organization_id))
            # asyncio.create_task(asyncio.create_task(push_summary_update(db, str(organization_id))))
        return str(obj.id)

    # --------------------------
    # Helper: Get Primary Logo URL
    # --------------------------
    def get_primary_logo(self, logos: dict) -> str:
        """Return the first URL from the logos dict if available, else a default."""
        if logos and isinstance(logos, dict):
            # Simply return the first value.
            for key, url in logos.items():
                if url:
                    ul = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME).extract_gcs_file_path(url)
                    print("logo url: ", ul)
                    return ul
        return "https://example.com/default-logo.png"

    # --------------------------
    # Helper: Build Email Template
    # --------------------------
    def build_account_email_html(self, row_data: dict, org_acronym: str, logo_url: str, login_href: str, pwd: str) -> str:
        """
        Build a dynamic HTML email template for account creation.
        The logo appears on top responsively, then a personalized salutation, account details, and a styled login button.
        """
        title = row_data.get("title") or ""
        first_name = row_data.get("first_name") or ""
        last_name = row_data.get("last_name") or ""
        email = row_data.get("email") or ""

        
        html_template = f"""
        <div style="max-width:600px;margin:0 auto;font-family:Arial,sans-serif;">
        <div style="text-align:center;padding:20px;">
            <img src="{logo_url}" alt="{org_acronym} Logo" style="max-width:200px; width:100%; height:auto;">
        </div>
        <div style="padding:20px;">
            <h2>{org_acronym} Staff Records System</h2>
            <p>Dear {title} {first_name} {last_name},</p>
            <p>Your account has been created successfully. 
            <br/>Your username is <strong>{email}</strong>.
            <br/>Your Password is <strong>{pwd}</strong>
            </p>
            <p>Please change your password upon your first login.</p>
            <p>Click on the login button to direct you to the Login Page </p>
            <div style="text-align:center;margin-top:30px;">
             <a href="{login_href}" style="display:inline-block;padding:10px 20px;background-color:#007bff;color:#fff;text-decoration:none;border-radius:4px;">Login</a> 
            </div>
            <p style="margin-top:30px;">Best regards,<br>{org_acronym} Team</p>
        </div>
        </div>
        """
        return html_template

    # --------------------------
    # Helper: Get Default Role (if missing)
    # --------------------------
    def get_or_create_default_role(self, db: Session, background_tasks: BackgroundTasks, organization_id: str) -> str:
        """
        If no role column is provided, check the organization's roles for a role named "Staff"
        with default permissions (e.g. view/edit own data only). If not found, create one.
        Return the role id as a string.
        """
        from Models.Tenants.role import Role  # adjust import as needed
        default_role_name = "Staff" or "Employee"
        default_permissions = []
        role_obj = db.query(Role).filter(
            Role.name.ilike(default_role_name),
            Role.organization_id == organization_id
        ).first()
        print("role_obj: ", role_obj)
        # If the role is found, return its ID.
        if not role_obj:
            # If the role is not found, we can use the default permissions from settings.
            # This is a fallback in case the role is not found in the database.
            # Locate the 'Employee' or 'staff' role configuration.
            role_config = next(
                (role_item for role_item in settings.DEFAULT_ROLE_PERMISSIONS
                    if role_item["name"].lower() in ("employee", "staff")),
                None
            )
            print("default function: ", role_config)
            # If a role configuration is found, use its permissions.
            if role_config:
                default_permissions = role_config.get("permissions", [])
                print("default_permissions in default function: ", default_permissions)
            # Create the new role with default permissions.
            role_obj = Role(
                name=default_role_name,
                permissions=default_permissions,
                organization_id=organization_id,
                
            )
            db.add(role_obj)
            db.commit()
            db.refresh(role_obj)
            background_tasks.add_task(push_summary_update, db, str(organization_id))
            # asyncio.create_task(push_summary_update(db, str(organization_id)))
        return str(role_obj.id)

    # ------------------------------------------------------------------------------
# 7. Excel date converter
# ------------------------------------------------------------------------------
    def maybe_convert_excel_date(self, value):
        """
        If value is a float/int, interpret it as an Excel date serial and convert to a real date.
        Otherwise, return as is.
        """
        if isinstance(value, (int, float)) and value > 59:  # Excel's leap day bug
            base_date = datetime(1899, 12, 30)
            try:
                dt = base_date + timedelta(days=float(value))
                return dt.date()
            except:
                return value
        return value
    



    # ------------------------------------------------------------------------------
# 7. Bulk Insert CRUD
# ------------------------------------------------------------------------------
  

    def generate_random_string(self, length=6) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))

   

    def bulk_insert_crud(self, organization_id: str, file: UploadFile, background_tasks: BackgroundTasks, db: Session, sms_svc: BaseSMSService = Depends(get_sms_service), conf: BaseConfig = Depends(get_config)  ) -> dict:
        # (1) Validate file extension.
        if not allowed_file(file.filename):
            raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed.")

        # (2) Read file contents.
        try:
            contents = file.file.read()
            file_stream = io.BytesIO(contents)
            if file.filename.lower().endswith("csv"):
                df = pd.read_csv(file_stream)
                sheets = {"default": df}
            else:
                sheets = pd.read_excel(file_stream, sheet_name=None)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

        success_records = []
        error_records = []
        failed_rows_by_sheet: Dict[str, List[int]] = {}

        # (3) Retrieve organization record.
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        logo_url = self.get_primary_logo(org.logos or {})
        logo_url = extract_items(logo_url)
        print(f"\norganization logo source: {logo_url}")
        org_acronym = get_organization_acronym(org.name)  # Or a function to get acronym.
        login_href = f"{org.access_url}/signin" if org.access_url else "https://example.com/login"

        # (4) Build an employee_map (lowercase email → employee ID) for linking related sheets.
        employee_map = {}   # email (lowercase) -> employee_id
        employee_list = []  # list of employee IDs in processing order
        emp_contacts = []

        # (5) Determine processing order: process sheets with highest employee field overlap first.
        sheet_order = sorted(
            sheets.items(),
            key=lambda item: len(set(item[1].columns.str.lower()).intersection(model_field_map["employee"])),
            reverse=True
        )
        # print("\n\nordered sheets: ", sheet_order)

        total_employee_rows = 0
        # ------------- PASS 1: Process Employee Records -------------
        for sheet_name, df in sheet_order:
            # print(f"\n\nsheet: {sheet_order}\nsheet_name: ", f"{sheet_name}\ncolumns: {df.columns}")
            sheet_lower = sheet_name.strip().lower()
            if sheet_lower in {"employee", "employees"} or len(set(df.columns.str.lower()).intersection(model_field_map["employee"])) >= 5:
                df.columns = [col.strip().lower() for col in df.columns]
                total_employee_rows += len(df)
                for index, row in df.iterrows():
                    row_data = {k: row[k] for k in df.columns}
                    row_data = sanitize_row_data(row_data)
                    try:
                        expected_fields = model_field_map["employee"]
                        ModelClass = model_classes["employee"]
                        model_data = {}
                        extra_data = {}
                        # Process each column using fuzzy matching.
                        for col_name, val in row_data.items():
                            concept = find_standard_concept(col_name)
                            # Map the concept to an expected field if possible.
                            for field in expected_fields:
                                if normalize_column_name(field) == normalize_column_name(concept):
                                    concept = field
                                    break
                            if concept in expected_fields and val is not None:
                                model_data[concept] = val
                            else:
                                if any(x in concept for x in ["address", "phone", "home address", "residential address","contact", "gps", "number", "mobile", "phone_number", "contact_number", "mobile_number", "telephone", "telephone_number"]):
                                    if concept in ["phone", "contact", "number", "mobile", "phone_number", "contact_number", "mobile_number", "telephone", "telephone_number"]:
                                        emp_contacts.append(val)

                                    extra_data[concept] = val
                                    
                        if extra_data:
                            model_data["contact_info"] = extra_data
                            # emp_contacts = extra_data
                        
                        print("\n\nemp_contact:: ", emp_contacts)
                        # Convert date fields.
                        for dcol in ["date_of_birth", "hire_date", "termination_date"]:
                            if dcol in model_data and model_data[dcol] is not None:
                                model_data[dcol] = parse_date_value(model_data[dcol])
                        # Add organization_id.
                        model_data["organization_id"] = organization_id
                        salary_value = None
                        transient_role_id = None

                        # --- Process Branch & Department ---
                        # Process branch from raw row data (not from model_data)
                        branch_id = None
                        branch_key = None
                        for key in row_data.keys():
                            if find_standard_concept(key).lower() == "branch":
                                branch_key = key
                                break
                        if branch_key:
                            branch_val = row_data.get(branch_key)
                            if branch_val:
                                branch_val = str(branch_val).strip()
                                branch_location = str(row_data.get("location", branch_val)).strip()
                                if org.nature.strip().lower() == "single managed":
                                    row_data.pop(branch_key, None)
                                    print(f"After pop {branch_key} from {row_data}")
                                    branch_id = None
                                    # model_data.pop(branch_key, None)
                                    # print(f"\n\nAfter {model_data} pop {branch_key}")
                                    # raise HTTPException(
                                    #     status_code=400,
                                    #     detail=f"Organization '{org.name}' is single managed; branch data is not allowed."
                                    # )
                                else:
                                    # Import Branch model from your organization module.
                                    from Models.Tenants.organization import Branch
                                    branch_id = self.process_related_field(db, background_tasks, organization_id, branch_val, Branch, "name", {"location": branch_location, "manager_id": None})
                        
                        print(f"branch_id = {branch_id}")
                        # Process department if present in model_data.
                        if "department" in model_data and model_data["department"]:
                            dept_val = str(model_data["department"]).strip()
                            defaults = {"branch_id": branch_id} if branch_id else {}
                            print(f"defaults = {defaults}")
                            dept_id = self.process_related_field(db,background_tasks, organization_id, dept_val, Department, "name", defaults)
                            print(f"processed department with id = {dept_id}")
                            model_data["department_id"] = dept_id
                            model_data.pop("department", None)

                        # --- Process Rank ---
                        if "rank" in model_data and model_data["rank"]:
                            rank_val = str(model_data["rank"]).strip()
                            rank_id = self.process_related_field(db, background_tasks, organization_id, rank_val, Rank, "name", {"min_salary": 0, "max_salary": None, "currency": "GHS"})
                            model_data["rank_id"] = rank_id
                            model_data.pop("rank", None)

                        # --- Process Employee Type ---
                        # Check for "employee type" or "employment type" in model_data.
                        # If found, process it and set employee_type_id.
                        # If not found, check for "employment type" in model_data.
                        # If found, process it and set employee_type_id.
                        # print("is employee type: ", model_data["employee type"])
                        print("calling employee type: ", model_data) 
                        print("row_data: ", row_data)
                        type_key = None
                        for key in row_data.keys():
                            if find_standard_concept(key).lower() == "employee_type":
                                type_key = key
                                break
                            
                        if type_key:
                            et_val = row_data.get(type_key)
                            if et_val:
                                et_val = str(et_val).strip()
                                print("employee type value: ", et_val)
                                et_id = self.process_related_field(db,background_tasks, organization_id, et_val, EmployeeType, "type_code", {})
                                model_data["employee_type_id"] = et_id
                                model_data.pop(type_key, None)
                        # if "employee type" in model_data and model_data["employee type"]:

                        #     et_val = str(model_data["employee type"]).strip()
                        #     print("employee type value: ", et_val)
                        #     et_id = self.process_related_field(db, organization_id, et_val, EmployeeType, "type_code", {})
                        #     model_data["employee_type_id"] = et_id
                        #     model_data.pop("employee type", None)
                        # elif "employment type" in model_data and model_data["employment type"]:
                        #     et_val = str(model_data["employment type"]).strip()
                        #     et_id = self.process_related_field(db, organization_id, et_val, EmployeeType, "type_code", {})
                        #     model_data["employee_type_id"] = et_id
                        #     model_data.pop("employment type", None)

                        transient_role_id = None
                        role_val = None

                        # 1. Dynamic Role Column Detection using Fuzzy Matching
                        ROLE_SYNONYMS = SYNONYMS_MAP.get('role', {'role'})
                        print(f"Role synonyms: {ROLE_SYNONYMS}")
                        # --- Process Role ---
                        if "role" in model_data and model_data["role"]:
                            role_val = str(model_data["role"]).strip()
                            # Look up role; if not found, create with default permissions if "staff"
                            existing_role = db.query(Role).filter(
                                Role.name.ilike(role_val),
                                Role.organization_id == organization_id
                            ).first()
                            if not existing_role:
                                default_perms = []
                                # if role_val.lower() == "staff":
                                    # Locate the 'Employee' or 'staff' role configuration.
                                role_config = next(
                                    (role_item for role_item in settings.DEFAULT_ROLE_PERMISSIONS
                                    if (role_val.lower() == role_item["name"].lower()) or (role_val.lower() in role_item["name"].lower()) ),
                                    None
                                )
                                print("role_config: ", role_config)
                                if role_config:
                                    default_perms = role_config.get("permissions", [])
                                    print("default_perms: ", default_perms)
                                # Create new role with default permissions.
                                print("creating new role: ", role_val)
                                new_role = Role(name=role_val, permissions=default_perms, organization_id=organization_id)
                                db.add(new_role)
                                db.commit()
                                db.refresh(new_role)
                                background_tasks.add_task(push_summary_update, db, str(organization_id))
                                # asyncio.create_task(push_summary_update(db, str(organization_id)))
                                transient_role_id = str(new_role.id)
                            else:
                                transient_role_id = str(existing_role.id)
                            model_data.pop("role", None)
                        else:
                            if not transient_role_id:
                                # If no role provided, use default role (e.g. "Staff" or "Employee").
                                # This is a fallback in case the role is not found in the database.
                                # Locate the 'Employee' or 'staff' role configuration.
                                transient_role_id = self.get_or_create_default_role(db, background_tasks, organization_id)
                            # transient_role_id = self.get_or_create_default_role(db, organization_id)

                        # --- Process Salary ---
                        if "salary" in model_data and model_data["salary"]:
                            try:
                                salary_value = float(model_data["salary"])
                            except Exception:
                                salary_value = None
                            model_data.pop("salary", None)

                        # Generate a random password.
                        transient_pwd = generate_random_string(6)

                        # Build the Employee record.
                        record = Employee(**model_data)
                        print("transient_role_id: ", transient_role_id)
                        # if transient_role_id:
                        setattr(record, "_role_id", transient_role_id)
                        setattr(record, "_plain_password", transient_pwd)
                        db.add(record)
                        db.flush()
                        background_tasks.add_task(push_summary_update, db, str(organization_id))
                        # asyncio.create_task(push_summary_update(db, str(organization_id)))
                        # # Update employee_map using lowercase email.
                        # if "email" in model_data and model_data["email"]:
                        #     employee_map[model_data["email"].lower()] = record.id
                        # Update employee_map and employee_list.
                        if "email" in model_data and model_data["email"]:
                            email_lower = model_data["email"].lower()
                            employee_map[email_lower] = record.id
                            employee_list.append(record.id)

                        # Create SalaryPayment record if salary provided.
                        if salary_value is not None:
                            sp = SalaryPayment(
                                employee_id=record.id,
                                rank_id=model_data.get("rank_id"),
                                amount=salary_value,
                                currency="GHS",
                                payment_date=datetime.utcnow(),
                                payment_method="Bank Transfer",
                                transaction_id=''.join(random.choices(string.ascii_letters + string.digits, k=12)),
                                status="Success"
                            )
                            db.add(sp)
                            db.flush()



                        db.commit()
                        success_records.append({
                            "sheet": sheet_name,
                            "row_index": index,
                            "model": "employee",
                            "data": row_data
                        })
                        background_tasks.add_task(push_summary_update, db, str(organization_id))
                        # asyncio.create_task(push_summary_update(db, str(organization_id)))

                        # Optionally send email notification.
                        if "email" in model_data and model_data["email"]:
                            try:
                                email_service = EmailService()
                                email_body = self.build_account_email_html(model_data, org_acronym, logo_url, login_href, transient_pwd)
                                background_tasks.add_task(
                                    email_service.send_html_email,
                                    background_tasks,
                                    [model_data["email"]],
                                    "Account Created Successfully",
                                    email_body
                                )
                            except Exception as e_email:
                                print(f"[WARN] Email notification failed for row {index}: {e_email}")
                        
                        try:
                            #send sms notification to employees by extracting phone or contact from contact_info dict
                            org = db.get(Organization, organization_id)
                            sender = get_organization_acronym(org.name) if org.name else conf.ARKESEL_SENDER_ID    #getattr(org.name, "sms_sender_id", conf.ARKESEL_SENDER_ID)
                            use_case= getattr(org, "sms_use_case", conf.ARKESEL_USE_CASE)

                            # print("\n\nemp_contacts for sms: ", emp_contacts)
                            if emp_contacts:
                                # Iterate over success_records, send SMS to each
                                for phone in emp_contacts:
                                    # print("\nphone: ", phone)
                                    if phone:
                                        sms_svc.send(
                                            phone,
                                            "employee_created",
                                            {"first_name": model_data["first_name"], "org_name": org.name, "email": model_data["email"]},
                                            sender_id=sender,
                                            use_case=use_case
                                        )
                                        print(f"SMS sent to {phone} for employee creation.")
                                    else:
                                        print(f"Phone number not found for employee {model_data['first_name']} {model_data['last_name']}")
                        except Exception as e_sms:
                            print(f"[WARN] SMS notification failed for row {index}: {e_sms}")

                        

                    except Exception as e:
                        db.rollback()
                        error_records.append({
                            "sheet": sheet_name,
                            "row_index": index,
                            "error": str(e),
                            "data": row_data
                        })
                        failed_rows_by_sheet.setdefault(sheet_name, []).append(index)
        # print("\n\nemployee_map: ", employee_map)
        # print("\n\nemployee_list: ", employee_list)
        # ------------- PASS 2: Process Additional Related Sheets -------------
        if not employee_map:
            print("No employee records processed; skipping related sheets.")
        else:
            for sheet_name, df in sheets.items():
                sheet_lower = sheet_name.strip().lower()
                if sheet_lower in {"employee", "employees"} or len(set(df.columns.str.lower()).intersection(model_field_map["employee"])) >= 5:
                    continue

                # print("\n\nother sheet: ", sheet_name, "\ncolumns: ", df.columns)
                df.columns = [col.strip().lower() for col in df.columns]

                # Determine best matching model by column overlap.
                model_choice = "dynamic"
                max_match = 0
                for mk, fields in model_field_map.items():
                    overlap = len(set(df.columns).intersection(fields))
                    if overlap > max_match:
                        max_match = overlap
                        model_choice = mk

                for index, row in df.iterrows():
                    row_data = sanitize_row_data(row.to_dict())
                    try:
                        expected_fields = model_field_map.get(model_choice, set())
                        ModelClass = model_classes.get(model_choice, None)
                        model_data = {}
                        for col_name, val in row_data.items():
                            concept = find_standard_concept(col_name)
                            if concept in expected_fields and val is not None:
                                # If this is a date field for the given model, convert it.
                                # Extend the set below with any additional date fields needed.
                                if concept in {"start_date", "end_date", "payment_date", "hire_date", "termination_date"}:
                                    model_data[concept] = parse_date_value(val)
                                # For numeric fields such as year_obtained, cast to int.

                                elif concept in {"year_obtained", "year_of_experience"} and val is not None:
                                    try:
                                        model_data[concept] = int(val)
                                    except Exception:
                                        model_data[concept] = None
                                elif concept in expected_fields and val is not None:
                                    model_data[concept] = val


                        # Link to employee via email if present.
                        if "email" in row_data and row_data["email"]:
                            emp_id = employee_map.get(row_data["email"].lower())
                            if emp_id:
                                model_data["employee_id"] = emp_id
                        # Otherwise, if no email column exists, try mapping by row order.
                        elif "employee_id" not in model_data:
                            # If the number of rows in this sheet matches the number of employee records processed,
                            # we assume they align by row order.
                            if index < len(employee_list):
                                model_data["employee_id"] = employee_list[index]
                        # If no employee_id is found, skip this record.
                        else:
                            print("row empty\n\n", row_data)

                        # If the model class is found, add organization_id if applicable.
                        if ModelClass and hasattr(ModelClass, "__table__") and "organization_id" in ModelClass.__table__.columns:
                            model_data["organization_id"] = organization_id
                        # print("\n\nnon-employee model class: ", ModelClass, "\nmodel_data: ", model_data)
                        # If the model class is not found, use the dynamic model.
                        if ModelClass:
                            record = ModelClass(**model_data)
                            db.add(record)
                            db.flush()
                        else:
                            from Models.dynamic_models import EmployeeDynamicData
                            record = EmployeeDynamicData(
                                employee_id=model_data.get("employee_id"),
                                data_category=sheet_name,
                                data=row_data
                            )
                            db.add(record)
                            db.flush()
                        db.commit()
                        success_records.append({
                            "sheet": sheet_name,
                            "row_index": index,
                            "model": model_choice,
                            "data": row_data
                        })
                        background_tasks.add_task(push_summary_update, db, str(organization_id))
                        # asyncio.create_task(push_summary_update(db, str(organization_id)))
                    except Exception as e:
                        db.rollback()
                        print("\n\nnon-employee models error")
                        error_records.append({
                            "sheet": sheet_name,
                            "row_index": index,
                            "error": str(e),
                            "data": row_data
                        })
                        failed_rows_by_sheet.setdefault(sheet_name, []).append(index)

        # Log errors if any.
        if error_records:
            err_log = BulkUploadError(
                organization_id=organization_id,
                file_name=file.filename,
                error_details=error_records
            )
            db.add(err_log)
            db.commit()
        
        # ---------------------- STEP 6: Compose Return Summary ----------------------
        total_rows = total_employee_rows
        success_count = len([r for r in success_records if r["model"] == "employee"])
        failure_count = len(error_records)

        # Compose message based on results.
        if success_count and not failure_count:
            msg = "Registered users should check their emails for access to the system."
        elif success_count and failure_count:
            # msg = (f"Employees should check their emails for access to the system; however, some records "
            #        "failed. Please review the failed records (see details below) and try manual insertion.\n**************************************************\n\t\tDetails\n**************************************************")
            # msg += "\n".join([f"Sheet: {r['sheet']}, Row: {r['row_index']}, Error: {r['error']}" for r in failed_rows_by_sheet])
            msg = ("Employees should check their emails for access to the system; however, some records "
                   "failed. Please review the failed records (see details below) and try manual insertion.")
        else:
            msg = "All records failed. Please review the errors and try again or register the records manually."

        # return {
        #     "detail": "Bulk upload processed.",
        #     "successful_records": success_records,
        #     "failed_records": error_records,
        #     "message": "Please review the failed records and try manual insertion if necessary."
        # }

        return {
            "detail": "Bulk upload processed.",
            "total_employee_rows": total_rows,
            "successful_inserts": len(success_records),
            "failed_inserts": failure_count,
            "failed_rows_by_sheet": failed_rows_by_sheet,
            "message": msg
        }



    # async def create_user(
    #         self,
    #     background_tasks: BackgroundTasks,
    #     db: Session,
    #     employee_data: dict,
    #     role_id: UUID,
    #     organization_id: UUID,
    #     image_file: UploadFile,
    #     created_by: Optional[UUID] = None,
    # ) -> Dict[str, str]:
    #     """
    #     Creates a user based on an existing employee record with bio authentication & secure image storage.
    #     """

    #     # Step 0: **Check if Organization Exists**
    #     org = db.query(Organization).filter(Organization.id == organization_id).first()
    #     if not org:
    #         raise HTTPException(status_code=404, detail="Can't Sign Up User under unknown Organization.")


    #     # Step 1: **Check if Employee Exists Based on Email**
    #     email = employee_data.get("email")
    #     employee = db.query(Employee).filter(Employee.email == email).first()
    #     if not employee:

    #         # Step 2: **Check if User Already Exists**
    #         existing_user = db.query(User).filter(User.email == email).first()
    #         if existing_user:
    #             raise HTTPException(status_code=400, detail="User account already exists for this employee.")

            
    #         # Step 3: **Check if Ro,e ID  Exists**
    #         findRole = db.query(Role).filter(Role.id == role_id).first()
    #         if not findRole:
    #             raise HTTPException(status_code=404, detail="Role Not Found.")
            

    #         existing_role = db.query(User).filter(User.role_id == role_id).first()
    #         if existing_role:
    #             raise HTTPException(status_code=400, detail="Role Already Assigned to Another User")
            
            
    #         # Step 4: **Check for Required Employee Fields**
    #         required_fields = ["title", "first_name", "last_name", "email"]
    #         for field in required_fields:
    #             if not employee_data.get(field):
    #                 raise HTTPException(status_code=400, detail=f"Missing required field: {field}")


    #         # Step 5: **Generate Credentials**
    #         user_name =  f"{employee_data.get('first_name').lower()}{employee_data.get('last_name').lower()}{ Security.generate_random_string(4)}" or  Security.generate_random_string(6)
    #         password =  Security.generate_random_char(6)
    #         hashed_password = self.hash_password(password)

            
                
    #         orgn = get_organization_acronym(org.name)
    #         # Step 7: **Upload Image to Google Cloud Storage**
    #         folder = f"organizations/{orgn}/user_profiles"
    #         gcs = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME)


    #         if image_file:
    #             logo_files = [{"filename": file.filename, "content": await file.read()} for file in image_file]
            
    #             image_url = gcs.upload_to_gcs(files=logo_files, folder=folder) or ""

    #             # Step 6: **Send Image File to External Bio Authentication API**
    #             # image_bytes = await image_file[0].read()
    #             # async with aiohttp.ClientSession(timeout=ClientTimeout(total=120)) as session:
    #             #     form = FormData()
    #             #     form.add_field("username", user_name)
    #             #     form.add_field("file", image_bytes, filename="image.jpg", content_type=image_file[0].content_type)

    #             #     try:
    #             #         logger.info(f"Sending facial auth request for {user_name} to {settings.FACIAL_AUTH_API_URL}")
    #             #         async with session.post(settings.FACIAL_AUTH_API_URL, data=form) as response:
    #             #             bio_auth_result = await response.json()
    #             #             logger.info(f"Response received: {bio_auth_result}")
    #             #             if response.status != 200:
    #             #                 raise HTTPException(status_code=500, detail=f"Bio authentication failed: {bio_auth_result}")
                            
    #             #             if response.status == 502:
    #             #                 logger.info(f"Response received: {response.status}: \nMeans the issue has to do with the external api itself not from the call.")
    #             #                 print(f"Response received: {response.status}: \nMeans the issue has to do with the external api itself not from the call.")
    #             #     except asyncio.TimeoutError:
    #             #         logger.error(f"Facial authentication timeout for {user_name}")
    #             #         raise HTTPException(status_code=504, detail="Facial authentication service timeout. Please try again.")

            
    #         # Step 8: **Create Employee Record**
    #         employee_record = Employee(
    #             first_name=employee_data["first_name"],
    #             middle_name=employee_data.get("middle_name"),
    #             last_name=employee_data["last_name"],
    #             title=employee_data.get("title", "Other"),
    #             gender=employee_data.get("gender", "Other"),
    #             date_of_birth=employee_data["date_of_birth"],
    #             marital_status=employee_data.get("marital_status", "Other"),
    #             email=email,
    #             contact_info=json.dumps(employee_data.get("contact_info", {})),
    #             hire_date=employee_data.get("hire_date"),
    #             termination_date=employee_data.get("termination_date"),
    #             is_active=True,
    #             custom_data=json.dumps(employee_data.get("custom_data", {})),
    #             profile_image_path=json.dumps(image_url) if isinstance(image_url, dict) else image_url,
    #             organization_id=organization_id,
    #         )
    #         # Optionally, set a transient attribute for the file listener:
    #         setattr(employee_record, "_uploaded_by_id", created_by if created_by else None)
    #         db.add(employee_record)
    #         db.commit()
    #         db.refresh(employee_record)

    #         # Log user creation
    #         # await self.log_audit(db, "CREATE", created_by, "employees" ,employee_record.id)


    #         # Step 9: **Create User & Employee Image Paths**
    #         user_record = User(
    #         username= user_name,
    #         email= email,
    #         hashed_password= hashed_password,
    #         role_id = role_id,
    #         organization_id = organization_id,
    #         is_active = True,
    #         image_path = json.dumps(image_url) if isinstance(image_url, dict) else image_url,  # Store in User model
    #         )
    #         # new_user = User(**user_data)
    #         db.add(user_record)
    #         db.commit()
    #         db.refresh(user_record)

        

    #         # Log user creation
    #         # self.log_audit(db, "CREATE", created_by, "users" ,user_record.id)

    #         email_service = EmailService()  # Instantiate the email service
    #         # Send email with credentials
    #         email_body = get_email_template(user_name, password, org.access_url, org.name)
    #         await email_service.send_email(background_tasks, recipients=[email], subject="Account Credentials", html_body=email_body)

        

    #         return {
    #             "id": str(user_record.id),
    #             # "id": user_record.id,
    #             "message": "User created successfully",
    #             "image_path": image_url,
    #         }
    #         # raise HTTPException(status_code=404, detail="Employee record not found. Register employee first.")
    #     else:
    #         logger.error(f"\n\nAn Employee with the Email '{employee_data.get('email')}' already exists.")
    #         raise HTTPException(status_code=404, detail="Email Already Exists.")

    # -----------------------------------------------------------------------------
# The create_user CRUD Function
# -----------------------------------------------------------------------------
    async def create_user(
        self,
        background_tasks: BackgroundTasks,
        db: Session,
        employee_data: dict,
        role_id: UUID,
        organization_id: UUID,
        image_file: Optional[UploadFile]=None,
        created_by: Optional[UUID] = None,
        storage: BaseStorage = Depends(get_storage_service),
        sms_svc: BaseSMSService = Depends(get_sms_service),
        config: BaseConfig = Depends(get_config),
    ) -> dict:
        """
        Creates a new user (employee) record from dynamic manager-supplied data.
        
        Steps:
        0. Verify Organization exists.
        1. Ensure no Employee or User with the same email exists.
        2. Validate required base fields.
        3. Check that Role exists.
        4. Generate credentials.
        5. Map UI keys using FIELD_SYNONYMS.
        6. Separate base fields from extra keys; merge extras into custom_data.
        7. Process 'employee_type' (lookup/create in EmployeeType).
        8. Process 'rank' (lookup in Rank).
        9. Extract next_of_kin data (expected as list).
        10. Process additional related data via RELATED_MODEL_MAP.
        11. Upload profile image.
        12. Send image file to external Facial Authentication API.
        13. Create the Employee record.
        14. Update related records with the new employee_id.
        15. Create NextOfKin records if provided.
        16. Create the User record.
        17. Infer managerial assignment from Role permissions and update Department or Branch accordingly.
        18. Send email with login credentials.
        19. Log audit events.
        """
        # Step 0: Verify Organization exists.
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        # Step 1: Check for existing Employee/User.
        email = employee_data.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email is required.")
        if db.query(Employee).filter(Employee.email == email).first():
            raise HTTPException(status_code=400, detail="Employee already exists.")
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=400, detail="User account already exists for this employee.")

        # Step 2: Validate required base fields.
        required_fields = {"first_name", "last_name", "email"}
        missing = [field for field in required_fields if not employee_data.get(field)]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

        # Step 3: Check that Role exists.
        role_obj = db.query(Role).filter(Role.id == role_id).first()
        if not role_obj:
            raise HTTPException(status_code=404, detail="Role not found.")

        # Step 4: Generate credentials.
        use_alias = f"{employee_data.get('first_name').lower()}{employee_data.get('last_name').lower()}{generate_random_string(4)}"
        #use employee email as username if it exists
        user_name = email if email else use_alias
        password = generate_random_string(6)
        hashed_password = pwd_context.hash(password)

        print(f"Generated credentials for {user_name} with plain password: {password} - this should be logged securely.\n\nits hash is: {hashed_password} merely for testing purposes.")

        # Step 5: Map UI keys.
        employee_data = map_employee_fields(employee_data)

        # Step 6: Separate base fields from extra fields.
        base_fields = {"first_name", "middle_name", "last_name", "title", "gender",
                    "date_of_birth", "marital_status", "email", "contact_info",
                    "hire_date", "termination_date", "staff_id", "profile_image_path"}
        base_employee_data = {k: employee_data[k] for k in employee_data if k in base_fields}
        extra_fields = {k: employee_data[k] for k in employee_data if k not in base_fields and k not in {"employee_type", "next_of_kin", "rank", "department", "branch", "Role"}}
        custom_data = employee_data.get("custom_data", {})
        if isinstance(custom_data, str):
            try:
                custom_data = json.loads(custom_data)
            except Exception:
                custom_data = {}
        custom_data.update(extra_fields)

        # Step 7: Process 'employee_type'.
        employee_type_id = None
        employee_type_value = employee_data.get("employee_type")
        if employee_type_value:
            employee_type_value = employee_type_value.strip()
            et_obj = db.query(EmployeeType).filter(
                EmployeeType.type_code.ilike(employee_type_value),
                EmployeeType.organization_id == organization_id
            ).first()
            if not et_obj:
                et_obj = EmployeeType(
                    type_code=employee_type_value,
                    description="",
                    default_criteria={},
                    organization_id=organization_id
                )
                db.add(et_obj)
                db.commit()
                db.refresh(et_obj)
            employee_type_id = et_obj.id
            asyncio.create_task(push_summary_update(db, str(organization_id)))

        # Step 8: Process 'rank' if provided.
        rank_id = None
        rank_value = employee_data.get("rank")
        if rank_value:
            rank_value = rank_value.strip()
            rank_obj = db.query(Rank).filter(
                Rank.name.ilike(rank_value),
                Rank.organization_id == organization_id
            ).first()
            if rank_obj:
                rank_id = rank_obj.id
            else:
                # Optionally, create a new Rank record.
                raise HTTPException(status_code=404, detail="Rank not found.")
        
        # Step 9: Extract department and branch if provided.
        department_id = None
        branch_id = None
        department_value = employee_data.get("department")
        branch_value = employee_data.get("branch")
        if department_value:
            department_value = department_value.strip()
            department_obj = db.query(Department).filter(
                or_(Department.name.ilike(department_value),
                Department.id == department_value
                ),
                Department.organization_id == organization_id
            ).first()
            if department_obj:
                department_id = department_obj.id
            else:
                raise HTTPException(status_code=404, detail="Department not found.")
        if branch_value:
            branch_value = branch_value.strip()
            branch_obj = db.query(Branch).filter(
                Branch.name.ilike(branch_value),
                Branch.organization_id == organization_id
            ).first()
            if branch_obj:
                branch_id = branch_obj.id
            else:
                raise HTTPException(status_code=404, detail="Branch not found.")
            

        # Step 9: Extract next_of_kin data.
        next_of_kin_list = employee_data.get("next_of_kin")
        
        # Step 10: Process additional related data via RELATED_MODEL_MAP.
        for related_key, (model_cls, expected_fields) in RELATED_MODEL_MAP.items():
            if related_key in employee_data:
                related_entries = employee_data.pop(related_key)
                if isinstance(related_entries, list):
                    for entry in related_entries:
                        filtered_data = {field: entry.get(field) for field in expected_fields if field in entry}
                        related_record = model_cls(employee_id=None, **filtered_data)
                        db.add(related_record)
                    db.commit()
                    asyncio.create_task(push_summary_update(db, str(organization_id)))
        
        # Step 11: Upload Profile Image.
        image_url = ""
        if image_file:
            org_acronym = get_organization_acronym(org.name)
            folder = f"organizations/{org_acronym}/user_profiles"
            # gcs = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME)
            file_content = await image_file.read()
            # image_url = gcs.upload_to_gcs(files=[{"filename": image_file.filename, "content": file_content}], folder=folder) or ""
            image_url = storage.upload(
            [{"filename": image_file.filename, "content": file_content, "content_type": image_file.content_type}],
            folder=folder,
        )

            # If image_url is a dict, select the first available URL.
            if isinstance(image_url, dict):
                image_url = next(iter(image_url.values()), "")
        
        # Step 12: Send image file to External Facial Authentication API.
        # if image_file:
        #     try:
        #         await image_file.seek(0)
        #         image_bytes = await image_file.read()
        #         timeout = ClientTimeout(total=120)
        #         async with aiohttp.ClientSession(timeout=timeout) as session:
        #             form = FormData()
        #             form.add_field("username", user_name)
        #             form.add_field("file", image_bytes, filename="image.jpg", content_type=image_file.content_type)
        #             async with session.post(settings.FACIAL_AUTH_API_URL, data=form) as response:
        #                 bio_auth_result = await response.json()
        #                 if response.status != 200:
        #                     raise HTTPException(status_code=500, detail=f"Bio authentication failed: {bio_auth_result}")
        #                 if response.status == 502:
        #                     print("External API returned 502; issue on external side.")
        #     except asyncio.TimeoutError:
        #         raise HTTPException(status_code=504, detail="Facial authentication service timeout. Please try again.")
        #     except Exception as e:
        #         print(f"Facial authentication error: {e}")
        
        # Step 13: Create the Employee record.
        # IMPORTANT: Remove contact_info from base_employee_data to avoid duplicate keyword argument.
        base_contact = base_employee_data.pop("contact_info", {})
        # Remove any existing key so we don’t pass it twice:
        base_employee_data.pop("profile_image_path", None)
        print("\n\nbase_employee_data: ", base_employee_data)
        employee_record = Employee(
            **base_employee_data,
            # contact_info=json.dumps(base_employee_data.get("contact_info", {})),
            contact_info=base_contact,  # Pass as a dict directly (for JSONB)
            custom_data=custom_data if custom_data else None,
            profile_image_path=image_url ,
            organization_id=organization_id,
            employee_type_id=employee_type_id,
            rank_id=rank_id,
            department_id=department_id if department_id else None,
            staff_id=employee_data.get("staff_id") if employee_data.get("staff_id") else None,
            is_active=True,
        )
        if created_by:
            setattr(employee_record, "_uploaded_by_id", created_by)
        setattr(employee_record, "_role_id", role_id) 
        setattr(employee_record, "_plain_password", password)
        if image_url:
            setattr(employee_record, "_user_image", image_url)
        db.add(employee_record)
        db.commit()
        db.refresh(employee_record)
        asyncio.create_task(push_summary_update(db, str(organization_id)))
        
        # Step 14: Update related records (from RELATED_MODEL_MAP) with the new employee_id.
        for related_key, (model_cls, _) in RELATED_MODEL_MAP.items():
            records = db.query(model_cls).filter(model_cls.employee_id == None).all()
            for rec in records:
                rec.employee_id = employee_record.id
            db.commit()
        
        # Step 15: Process next_of_kin records.
        if next_of_kin_list and isinstance(next_of_kin_list, list):
            for kin in next_of_kin_list:
                nok_record = NextOfKin(
                    employee_id=employee_record.id,
                    name=kin.get("name"),
                    relation=kin.get("relation"),
                    phone=kin.get("phone"),
                    address=kin.get("address"),
                    details=kin.get("details")
                )
                db.add(nok_record)
            db.commit()
            asyncio.create_task(push_summary_update(db, str(organization_id)))
        
        # Step 16: Create the User record.
        # user_record = User(
        #     username=user_name,
        #     email=email,
        #     hashed_password=hashed_password,
        #     role_id=role_id,
        #     organization_id=organization_id,
        #     is_active=True,
        #     image_path=image_url,
        # )
        # db.add(user_record)
        # db.commit()
        # db.refresh(user_record)
        
        # Step 17: Infer managerial assignment from Role permissions.
        # Here, we assume Role.permissions is a JSON object that may include keys:
        # "is_department_head": true or "is_branch_manager": true.
        permissions = role_obj.permissions or []
        # If the role implies Head of Department and the UI provided a department assignment:
        if "department:head:dashboard" in permissions:
            # We try to get the department assignment from either the "department" key
            # or from the synonym "assigned_dept".
            dept_identifier = employee_data.get("department") or employee_data.get("assigned_dept")
            if dept_identifier:
                try:
                    # If the provided identifier is a UUID, use it directly
                    dept_id = UUID(dept_identifier)
                except ValueError:
                    # Otherwise, assume it's a department name.
                    dept_obj = db.query(Department).filter(Department.name.ilike(dept_identifier), Department.organization_id == organization_id).first()
                    dept_id = dept_obj.id if dept_obj else None
                if dept_id:
                    dept_obj = db.query(Department).filter(Department.id == dept_id).first()
                    if dept_obj:
                        dept_obj.department_head_id = employee_record.id
                        db.commit()
                        asyncio.create_task(push_summary_update(db, str(organization_id)))
        # If the role's permissions indicate the employee is a branch manager.
        if "branch:manager" in permissions:
            branch_identifier = employee_data.get("branch")
            if branch_identifier:
                try:
                    branch_id = UUID(branch_identifier)
                except ValueError:
                    branch_obj = db.query(Branch).filter(Branch.name.ilike(branch_identifier), Branch.organization_id == organization_id).first()
                    branch_id = branch_obj.id if branch_obj else None
                if branch_id:
                    branch_obj = db.query(Branch).filter(Branch.id == branch_id).first()
                    if branch_obj:
                        branch_obj.manager_id = employee_record.id
                        db.commit()
                        asyncio.create_task(push_summary_update(db, str(organization_id)))
        
        # Optionally, if the UI sends explicit department/branch IDs, assign them.
        if "department" in employee_data:
            try:
                dept_id = UUID(employee_data["department"])
                dept_obj = db.query(Department).filter(Department.id == dept_id, Department.organization_id == organization_id).first()
                if dept_obj:
                    employee_record.department_id = dept_id
                    db.commit()
                    asyncio.create_task(push_summary_update(db, str(organization_id)))
            except Exception:
                pass
        if "branch" in employee_data:
            try:
                branch_id = UUID(employee_data["branch"])
                # Additional branch assignment logic can be added here.
                db.commit()
                asyncio.create_task(push_summary_update(db, str(organization_id)))
            except Exception:
                pass
         
        logos = org.logos
        logo = next(iter(logos.values())) if len(logos) > 1 else logos

        # Step 18: Send email with login credentials using template.
        email_service = EmailService()
        template_data = {
            "organization_name": org.name,
            "employee_name": f"{base_employee_data.get('title', '')} {base_employee_data.get('first_name', '')} {base_employee_data.get('last_name', '')}".strip(),
            "user_avatar": "👤",  # Default avatar emoji
            "username": email,
            "password": password,
            "login_url": org.access_url + "/signin"
        }
        await email_service.send_email(
            background_tasks, 
            recipients=[email], 
            subject=f"Welcome to {org.name} - Your Account is Ready",
            template_name="organization_created.html",
            template_data=template_data
        )

         # 18. **Send SMS** via injected sms_svc
        phone = base_employee_data.get("contact_info", {}).get("contact") or base_employee_data.get("contact_info", {}).get("phone") or \
            base_employee_data.get("contact_info", {}).get("phone_number") or base_employee_data.get("contact_info", {}).get("mobile") or \
            base_employee_data.get("contact_info", {}).get("mobile_number") or base_employee_data.get("contact_info", {}).get("contact_number") or \
            base_employee_data.get("contact_info", {}).get("telephone_number") or base_employee_data.get("contact_info", {}).get("telephone")
        
        if phone:
            sender  = get_organization_acronym(org.name) or getattr(org, "sms_sender_id", config.ARKESEL_SENDER_ID)
            use_case = getattr(org, "sms_use_case", config.ARKESEL_USE_CASE)
            signin_url = (org.access_url or config.API_BASE_URL) + "/signin"
            background_tasks.add_task(
                sms_svc.send,
                phone,
                "employee_created",
                {"first_name": base_employee_data["first_name"], "org_name": org.name, "email": base_employee_data["email"]},
                sender_id=sender,
                use_case=use_case
            )
        asyncio.create_task(push_summary_update(db, str(org.id)))
        # Step 19: Log audit events.
        self.log_audit(db, "CREATE", created_by, "employees", employee_record.id)
        # await self.log_audit(db, "CREATE", created_by, "users", user_record.id)
        print("\n\nUser Created Successfully")
        return {
            # "id": str(user_record.id),
            "message": "User created successfully",
            # "image_path": image_url if image_url else None,
        }



    async def update_user(
        self,
        background_tasks: BackgroundTasks,
        db: Session,
        user_id: UUID,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role_id: Optional[UUID] = None,
        image_file: Optional[UploadFile] = None,
        config: BaseConfig  = Depends(get_config),
        storage: BaseStorage   = Depends(get_storage_service),
        sms_svc: BaseSMSService  = Depends(get_sms_service),
    ) -> Dict[str, str]:
        """
        Dynamically updates a user's details while ensuring security, efficiency, and business logic integrity.

        :param background_tasks: BackgroundTasks for async email notifications.
        :param db: Database session.
        :param user_id: The ID of the user being updated.
        :param username: (Optional) New username.
        :param email: (Optional) New email.
        :param role_id: (Optional) New role ID.
        :param image_file: (Optional) New profile image file.
        :return: Dictionary containing a success message.
        """

        if not user_id:
            raise HTTPException(status_code=400, detail="User Identifier (user_id) is required.")

        # Fetch user and employee records
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        employee = db.query(Employee).filter(Employee.email == user.email).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Associated employee record not found.")
        
        

        update_fields = {}

        # 🚫 **Ensure Organization ID is Immutable**
        organization_id = user.organization_id
        organization = db.query(Organization).filter(Organization.id == organization_id).first()

        if not organization:
            raise HTTPException(status_code=404, detail="Associated organization not found.")

        # ✅ **Handle Email Updates**
        if email and email != user.email:
            email_exists = db.query(User).filter(User.email == email, User.id != user_id).first()
            if email_exists:
                raise HTTPException(status_code=400, detail="Email is already in use.")

            update_fields["email"] = email
            employee.email = email  # Ensure Employee email syncs with User

        # ✅ **Handle Username Updates & External API Trigger**
        if username and username != user.username:
            username_exists = db.query(User).filter(User.username == username, User.id != user_id).first()
            if username_exists:
                raise HTTPException(status_code=400, detail="Username is already taken.")

            # Retrieve existing image from Google Cloud Storage
            gcs = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME)
            image_data = gcs.download_from_gcs(user.image_path) if user.image_path else None

            

            # Call External API for Facial Authentication Username Update
            if image_data:
                async with aiohttp.ClientSession(timeout=ClientTimeout(total=120)) as session:
                    form = FormData()
                    form.add_field("new_username", username)
                    form.add_field("file", image_data, filename="image.jpg", content_type="image/jpeg")

                    try:
                        async with session.put(f"{settings.FACIAL_AUTH_API_URL}/update/{user.username}", data=form) as response:
                            if response.status == 502:
                                logger.warning(f"External API deployment issue detected: {response.status}. Issue is with the API, not the request.")
                            elif response.status != 200:
                                raise HTTPException(status_code=500, detail="Failed to update facial authentication system.")
                    except asyncio.TimeoutError:
                        raise HTTPException(status_code=504, detail="External API timeout. Please try again.")

            update_fields["username"] = username

        # ✅ **Handle Role Updates**
        if role_id and role_id != user.role_id:
            role = db.query(Role).filter(Role.id == role_id, Role.organization_id == organization_id).first()
            if not role:
                raise HTTPException(status_code=400, detail="Invalid role ID for this organization.")

            update_fields["role_id"] = role_id

        # ✅ **Handle Profile Image Updates**
        if image_file:
            gcs = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME)

            # Delete old image from Google Cloud if it exists
            if user.image_path:
                gcs.delete_from_gcs(user.image_path)
            
            # Upload new image
            org_acronym = get_organization_acronym(org.name)
            folder = f"organizations/{org_acronym}/user_profiles"
            file_content = await image_file.read()
            new_image_url = storage.upload(
            [{"filename": image_file.filename, "content": file_content, "content_type": image_file.content_type}],
            folder=folder,
            )

            # Upload new image
            # folder = f"organizations/{organization.name}/user_profiles"
            # new_image_url = gcs.upload_to_gcs(
            #     [{"filename": image_file.filename, "content": await image_file.read()}],
            #     folder
            # )

            update_fields["image_path"] = new_image_url
            employee.profile_image_path = new_image_url  # Ensure Employee profile image is updated

        # ✅ **Apply Updates if Any**
        if update_fields:
            for field, value in update_fields.items():
                setattr(user, field, value)

            db.commit()
        else:
            raise HTTPException(status_code=400, detail="No valid update fields provided.")

        # ✅ **Send Email Notification**
        email_service = EmailService()

        email_body = get_update_notification_email_template(
            username=user.username,
            organization=organization,
        )
        # background_tasks.add_task(email_service.send_email, recipients=[user.email], subject="Account Update", html_body=email_body)
       
        background_tasks.add_task(
            email_service.send_html_email,
            background_tasks,
            [user.email],
            "Account Update",
            email_body
        )
        

        org = db.query(Organization).filter(Organization.id == user.organization_id).first()
        ci = employee.get("contact_info", {})
        # if someone accidentally sent a JSON‐string in contact_info, try decode
        if isinstance(ci, str):
            try:
                ci = json.loads(ci)
            except:
                print("\ncouldn't retrieve contact from str instance.\n")
        if not isinstance(ci, dict):
            print("couldn't retrieve contact from dict instance.\n")

        phone = ci.get("phone".lower()) or ci.get("mobile".lower()) or ci.get("contact".lower()) or ci.get("phone number".lower()) or \
                ci.get("phone_number".lower()) or ci.get("mobile number".lower()) or ci.get("mobile_number".lower()) or \
                ci.get("contact number".lower()) or ci.get("contact_number".lower())
        if not phone:
            print("\nno phone or contact identified in contact_info.\n")

        else:
            sender  = get_organization_acronym(org.name) or getattr(org, "sms_sender_id", config.ARKESEL_SENDER_ID)
            use_case = getattr(org, "sms_use_case", config.ARKESEL_USE_CASE)
            background_tasks.add_task(
                sms_svc.send,
                phone,
                "user_account_updated",
                {"first_name": employee["first_name"], "org_name": org.name},
                sender_id=sender,
                use_case=use_case
            )
        
        asyncio.create_task(push_summary_update(db, str(organization_id)))
        return {"message": "User updated successfully."}



        


    async def authenticate_user(db: Session, username: str, password: str, request) -> Dict:
        """
        Authenticates a user while enforcing rate limits and logging failed login attempts.
        """
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Apply rate limit before authentication
        rate_limiter.check_rate_limit(db, user, request)

        # Verify password
        if not  global_security.verify_password(password, user.hashed_password):
            rate_limiter.log_failed_attempt(user, request)  # Log failed attempt
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Reset failed login attempts on success
        rate_limiter.reset_attempts(user)

        # Generate JWT Token
        token_data = {
            "user_id": str(user.id),
            "username": user.username,
            "role_id": str(user.role_id),
            "organization_id": str(user.organization_id),
        }
        token =  global_security.generate_token(token_data)

        return {
            "username": user.username,
            "email": user.email,
            "token": token,
            "token_expiration": datetime.datetime.utcnow() + datetime.timedelta(seconds=3600),
            "role": user.role.name,
            "permissions": user.role.permissions,
            "organization_id": user.organization_id,
            "organization_name": user.organization.name,
            "access_url": user.organization.access_url,
            "dashboard_data": user.organization.dashboards,
            "settings_name": user.organization.settings,
        }
    


async def create_ceo_account(
    self,
    db: AsyncSession,
    organization_data: OrganizationCreateSchema,
    background_tasks: BackgroundTasks,
) -> Dict[str, str]:
    """
    Creates an organization, CEO role, and CEO user account.
    Automatically sends an email with username and password.
    """
    try:
        # Step 1: Create Organization
        organization = self.org_model(**organization_data.dict())
        db.add(organization)
        await db.commit()
        await db.refresh(organization)

        # Step 2: Create CEO Role
        permissions = get_permissions_from_db(db, "CEO")
        # role_data = {
        #     "name": "CEO",
        #     "permissions": permissions,
        #     "organization_id": organization.id,
        # }
            # Step 2: Create CEO Role
        role_data = await self.role_cache.get_or_create_role(
            db, self.role_model, "CEO", permissions, organization.id
        )
        role = self.role_model(**role_data)
        db.add(role)
        await db.commit()
        await db.refresh(role)

        # Step 3: Create CEO User
        username = generate_random_string(USERNAME_LENGTH)
        password = generate_random_string(PASSWORD_LENGTH)
        hashed_password = self.hash_password(password)

        user_data = {
            "username": username,
            "email": organization_data.email,
            "hashed_password": hashed_password,
            "role_id": role.id,
            "organization_id": organization.id,
            "is_active": True,
        }
        user = self.user_model(**user_data)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Step 4: Send Email to CEO
        email_body = (
            f"<h1>Welcome to the System!</h1>"
            f"<p>Your account has been created with the following details:</p>"
            f"<ul><li>Username: {username}</li><li>Password: {password}</li></ul>"
            f"<p>Please log in and change your password immediately.</p>"
        )
        # send_email(
        #     to_email=organization_data.email,
        #     subject="Your Account Details",
        #     body=email_body,
        #     background_tasks=background_tasks,
        # )

        background_tasks.add_task(
            send_email_async, organization_data.email, "Your Account Details", email_body, db, self.audit_model, user.id
        )

        # # Log Audit
        # await self.log_audit(db, "create_ceo_account", user.id, "users", user.id)

        # Log Audit
        await log_audit(db, self.audit_model, "create_ceo_account", user.id, "users", user.id)

        return {"message": "CEO account created successfully.", "username": username, "password": password}

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create CEO account: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create CEO account: {str(e)}"
        )

async def create_employee_user(
    self,
    db: AsyncSession,
    employee_data: EmployeeCreateSchema,
    performed_by: Optional[UUID],
    background_tasks: BackgroundTasks,
) -> Dict[str, str]:
    """
    Creates a user account for an existing employee.
    Automatically sends an email with username and password.
    """
    try:
        # Fetch Employee Details
        employee = (
            await db.query(self.employee_model)
            .filter(self.employee_model.id == employee_data.employee_id)
            .first()
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Check if User Already Exists
        existing_user = (
            await db.query(self.user_model)
            .filter(self.user_model.email == employee.email)
            .first()
        )
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="User account already exists for this employee",
            )

        # Generate Username and Password
        username = generate_random_string(USERNAME_LENGTH)
        password = generate_random_string(PASSWORD_LENGTH)
        hashed_password = self.hash_password(password)

        # Create User Account
        user_data = {
            "username": username,
            "email": employee.email,
            "hashed_password": hashed_password,
            "role_id": employee.role_id,
            "organization_id": employee.organization_id,
            "is_active": True,
        }
        user = self.user_model(**user_data)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Send Email to Employee using template
        template_data = {
            "organization_name": employee.organization.name if hasattr(employee, 'organization') and employee.organization else "Organization",
            "employee_name": f"{employee.title or ''} {employee.first_name} {employee.last_name}".strip(),
            "user_avatar": "👤",  # Default avatar emoji
            "username": username,
            "password": password,
            "login_url": (employee.organization.access_url if hasattr(employee, 'organization') and employee.organization else "") + "/signin"
        }
        
        # Use the template-based email sending
        email_service = EmailService()
        background_tasks.add_task(
            email_service.send_email,
            background_tasks,
            recipients=[employee.email],
            subject=f"Welcome to {template_data['organization_name']} - Your Account is Ready",
            template_name="organization_created.html",
            template_data=template_data
        )

        # Log Audit
        # await self.log_audit(db, "create_employee_user", performed_by, "users", user.id)

        # Log Audit
        await log_audit(db, self.audit_model, "create_employee_user_account", performed_by, "users", user.id)

        asyncio.create_task(push_summary_update(db, str(employee.organization_id)))
        return {"message": "Employee account created successfully.", "username": username, "password": password}

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create employee user account: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create employee user account: {str(e)}",
        )

async def bulk_create_users_from_file(
    self,
    db: AsyncSession,
    file: UploadFile,
    current_user: Dict,
    background_tasks: BackgroundTasks,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Bulk create user accounts from a file.
    """
    if file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
        raise HTTPException(
            status_code=400,
            detail="Only CSV and Excel files are supported."
        )

    results = []
    try:
        # Load file content
        content = file.file.read()
        if file.content_type == "text/csv":
            data = pd.read_csv(io.StringIO(content.decode("utf-8")))
        else:
            data = pd.read_excel(io.BytesIO(content))

        # Normalize column names
        data.columns = [col.lower().strip() for col in data.columns]

        # Validate file structure
        validate_file_structure(
            data,
            ["name", "dob", "email", "contact", "position"]
        )

        # Determine organization ID from the current user's session
        organization_id = current_user.get("organization_id")
        if not organization_id:
            raise HTTPException(
                status_code=403,
                detail="Current user's organization could not be determined. Ensure you are logged in."
            )

        semaphore = asyncio.Semaphore(10)

        async def process_row(row):
            async with semaphore:
                try:
                    email = row.get("email")
                    if not email:
                        raise ValueError("Email is required but missing.")
                    
                    if not email or not Validator.is_valid_email(email):
                        return { "status": "failed", "error": "Invalid or missing email"}


                    # Check if user already exists
                    existing_user = await db.query(self.user_model).filter(
                        self.user_model.email == email
                    ).first()
                    if existing_user:
                        return {"email": email, "status": "failed", "error": "User already exists"}
                    
                    dob = row.get("dob")
                    if not Validator.is_valid_dob(dob):
                        return { "status": "failed", "error": "Invalid DOB"}

                    # Generate username and password
                    username = generate_random_string(USERNAME_LENGTH)
                    password = generate_random_string(PASSWORD_LENGTH)
                    hashed_password = self.hash_password(password)

                    # Determine role and permissions
                    position = row.get("position", "staff")
                    job_description = row.get("job_description", DEFAULT_PERMISSIONS.get("staff"))

                    # Check if the role already exists
                    # role = await db.query(self.role_model).filter(
                    #     self.role_model.name == position,
                    #     self.role_model.organization_id == organization_id
                    # ).first()

                    # Retrieve or create role
                    role = await self.role_cache.get_or_create_role(
                        db, self.role_model, position, job_description, organization_id
                    )

                    if not role:
                        role = self.role_model(
                            name=position,
                            permissions=job_description,
                            organization_id=organization_id,
                        )
                        db.add(role)
                        await db.commit()
                        await db.refresh(role)

                    # Create user record
                    user = self.user_model(
                        username=username,
                        email=email,
                        hashed_password=hashed_password,
                        role_id=role.id,
                        organization_id=organization_id,
                        is_active=True,
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)

                    # Send email notification using template
                    template_data = {
                        "organization_name": "Organization",  # You might want to get this from the organization_id
                        "employee_name": f"{row.get('title', '')} {row.get('first_name', '')} {row.get('last_name', '')}".strip(),
                        "user_avatar": "👤",  # Default avatar emoji
                        "username": username,
                        "password": password,
                        "login_url": "/signin"  # You might want to get the full URL from organization
                    }
                    
                    email_service = EmailService()
                    background_tasks.add_task(
                        email_service.send_email,
                        background_tasks,
                        recipients=[email],
                        subject=f"Welcome to {template_data['organization_name']} - Your Account is Ready",
                        template_name="organization_created.html",
                        template_data=template_data
                    )
                    # Log audit for successful user creation
                    await self.log_audit(
                        db=db,
                        action="bulk_user_creation_success",
                        performed_by=current_user["id"],
                        table_name="users",
                        record_id=user.id,
                    )

                    return {"email": email, "status": "success", "username": username, "password": password}

                except Exception as e:
                    logger.error(f"Failed to create user for email {row.get('email')}: {str(e)}")
                    return {"email": row.get("email"), "status": "failed", "error": str(e)}

        # Process rows concurrently
        tasks = [process_row(row) for _, row in data.iterrows()]
        results = await asyncio.gather(*tasks)

        return {"message": "Bulk user creation completed.", "results": results}

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to bulk create users: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Bulk user creation failed: {str(e)}"
        )
    

    
# async def bulk_create_users_from_file(
#     self,
#     db: AsyncSession,
#     file: UploadFile,
#     current_user: Dict,
#     background_tasks: BackgroundTasks,
# ) -> Dict[str, List[Dict[str, str]]]:
#     """
#     Bulk create user accounts from a file.
#     Extract relevant data and automatically assign missing fields where necessary.
#     """
#     if file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
#         raise HTTPException(
#             status_code=400,
#             detail="Only CSV and Excel files are supported."
#         )

#     results = []
#     try:
#         # Load file content
#         content = file.file.read()
#         if file.content_type == "text/csv":
#             data = pd.read_csv(io.StringIO(content.decode("utf-8")))
#         else:
#             data = pd.read_excel(io.BytesIO(content))

#         # Normalize column names
#         data.columns = [col.lower().strip() for col in data.columns]

#         # Mapping columns to expected fields
#         column_map = {
#             "name": ["name", "first name", "middle name", "last name", "surname"],
#             "dob": ["date of birth", "dob", "d.o.b"],
#             "email": ["email", "email address", "e-mail", "e-mail address"],
#             "contact": ["contact", "phone", "phone number", "telephone"],
#             "position": ["position", "role", "rank"],
#             "job_description": ["job description", "job", "tasks"]
#         }

#         def get_column(data: pd.DataFrame, possible_names: List[str]) -> pd.Series:
#             """Retrieve the column data for the first matching name in possible_names."""
#             for name in possible_names:
#                 if name in data.columns:
#                     return data[name]
#             return pd.Series([None] * len(data), name="unknown")

#         # Extract columns
#         name_col = get_column(data, column_map["name"])
#         dob_col = get_column(data, column_map["dob"])
#         email_col = get_column(data, column_map["email"])
#         contact_col = get_column(data, column_map["contact"])
#         position_col = get_column(data, column_map["position"])
#         job_description_col = get_column(data, column_map["job_description"])

#         # Determine organization ID from the current user's session
#         organization_id = current_user.get("organization_id")
#         if not organization_id:
#             raise HTTPException(
#                 status_code=403,
#                 detail="Current user's organization could not be determined. Ensure you are logged in."
#             )

#         # Iterate through rows and create users
#         for idx, row in data.iterrows():
#             try:
#                 email = email_col.iloc[idx]
#                 if not email:
#                     raise ValueError("Email is required but missing.")

#                 # Check if user already exists
#                 existing_user = await db.query(self.user_model).filter(
#                     self.user_model.email == email
#                 ).first()
#                 if existing_user:
#                     results.append(
#                         {
#                             "email": email,
#                             "status": "failed",
#                             "error": "User already exists",
#                         }
#                     )
#                     # Log audit for failed user creation
#                     await self.log_audit(
#                         db=db,
#                         action="bulk_user_creation_failed",
#                         performed_by=current_user["id"],
#                         table_name="users",
#                         record_id=None,
#                     )
#                     continue

#                 # Generate username and password
#                 username = generate_random_string(USERNAME_LENGTH)
#                 password = generate_random_string(PASSWORD_LENGTH)
#                 hashed_password = self.hash_password(password)

#                 # Determine role and permissions
#                 position = position_col.iloc[idx] or "staff"
#                 job_description = job_description_col.iloc[idx]

#                 # Check if the role already exists
#                 role = await db.query(self.role_model).filter(
#                     self.role_model.name == position,
#                     self.role_model.organization_id == organization_id
#                 ).first()

#                 if not role:
#                     # Insert role with default permissions if it doesn't exist
#                     role_permissions = job_description or {
#                         "create_task": True,
#                         "view_task": True,
#                         "update_task": False,
#                         "delete_task": False,
#                     }

#                     role_data = {
#                         "name": position,
#                         "permissions": role_permissions,
#                         "organization_id": organization_id,
#                     }
#                     role = self.role_model(**role_data)
#                     db.add(role)
#                     await db.commit()
#                     await db.refresh(role)

#                 # Create user record
#                 user_data = {
#                     "username": username,
#                     "email": email,
#                     "hashed_password": hashed_password,
#                     "role_id": role.id,
#                     "organization_id": organization_id,
#                     "is_active": True,
#                 }
#                 user = self.user_model(**user_data)
#                 db.add(user)
#                 await db.commit()
#                 await db.refresh(user)

#                 # Send email notification
#                 email_body = (
#                     f"<h1>Your Account Details</h1>"
#                     f"<p>Your account has been created with the following details:</p>"
#                     f"<ul><li>Username: {username}</li><li>Password: {password}</li></ul>"
#                     f"<p>Please log in and change your password immediately.</p>"
#                 )
#                 send_email(to_email=email, subject="Your Account Details", body=email_body, background_tasks=background_tasks)

#                 # Append success result
#                 results.append(
#                     {
#                         "email": email,
#                         "status": "success",
#                         "username": username,
#                         "password": password,
#                     }
#                 )

#                 # Log audit for successful user creation
#                 await self.log_audit(
#                     db=db,
#                     action="bulk_user_creation_success",
#                     performed_by=current_user["id"],
#                     table_name="users",
#                     record_id=user.id,
#                 )

#             except Exception as e:
#                 logger.error(f"Failed to create user for email {email}: {str(e)}")
#                 results.append(
#                     {
#                         "email": email,
#                         "status": "failed",
#                         "error": str(e),
#                     }
#                 )
#                 # Log audit for failed user creation
#                 await self.log_audit(
#                     db=db,
#                     action="bulk_user_creation_failed",
#                     performed_by=current_user["id"],
#                     table_name="users",
#                     record_id=None,
#                 )

#         return {"message": "Bulk user creation completed.", "results": results}

#     except Exception as e:
#         await db.rollback()
#         logger.error(f"Failed to bulk create users: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail=f"Bulk user creation failed: {str(e)}"
#         )


