import io
import random
import secrets
import string
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional, Union

import pandas as pd
from fastapi import HTTPException, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from Models.Tenants.organization import (Branch, Organization, Rank)
from Models.dynamic_models import EmployeeDynamicData, BulkUploadError
from Models.models import (Employee, User, Department, EmployeePaymentDetail,
                           AcademicQualification, EmergencyContact, EmployeeType,
                           EmploymentHistory, ProfessionalQualification, NextOfKin,
                           SalaryPayment)
from Utils.rate_limiter import RateLimiter
from Schemas.schemas import OrganizationCreateSchema, EmployeeCreateSchema
from Models.Tenants.role import Role
from datetime import datetime, date, timedelta
import re
from rapidfuzz import process, fuzz
from Utils.util import  get_organization_acronym
from Utils.config import DevelopmentConfig
from Utils.security import Security
from Service.email_service import EmailService, get_email_template





# --------------------------
# Helper: Process Related Field
# --------------------------
def process_related_field(self, db: Session, organization_id: str, value: str, table, lookup_field: str, defaults: dict) -> str:
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
                return url
    return "https://example.com/default-logo.png"

# --------------------------
# Helper: Build Email Template
# --------------------------
def build_account_email_html(row_data: dict, org_acronym: str, logo_url: str, login_href: str, pwd: str) -> str:
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
def get_or_create_default_role(self, db: Session, organization_id: str) -> str:
    """
    If no role column is provided, check the organization's roles for a role named "Staff"
    with default permissions (e.g. view/edit own data only). If not found, create one.
    Return the role id as a string.
    """
    from Models.Tenants.role import Role  # adjust import as needed
    default_role_name = "Staff"
    default_permissions = {"view": "own", "edit": "own", "request": ["department head", "HR"]}
    role_obj = db.query(Role).filter(
        Role.name.ilike(default_role_name),
        Role.organization_id == organization_id
    ).first()
    if not role_obj:
        role_obj = Role(name=default_role_name, permissions=default_permissions, organization_id=organization_id)
        db.add(role_obj)
        db.commit()
        db.refresh(role_obj)
    
    return str(role_obj.id)


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




# ------------------------------------------------------------------------------
# 1. Column Synonyms
# ------------------------------------------------------------------------------
# We define synonyms for each concept. Example:
SYNONYMS_MAP = {
    "first_name": {"first_name", "first", "fname", "first name", "firstname", "Given Name", "Given Name (First Name)", "given name", "givenname"},
    "middle_name": {"middle_name", "middle", "mname", "middle name", "middlename", "Middle Name", "Middle Name (Middle Name)", "middle name"},
    "last_name": {"last_name", "last", "lname", "last name", "lastname", "Family Name", "Surname", "Surname (Family Name)", "surname", "family name", "familyname"},
    "title": {"title", "salutation", "prefix", "name prefix", "name prefix (title)", "name prefix (salutation)", "name prefix (prefix)"},
    "department": {"department", "dept", "division", "section", "unit", "department name", "department name (dept)", "department name (division)", "department name (section)", "department name (unit)"},
    "role": {"role", "job role", "job", "position", "post", "system role", "job description", "job title", "job title (role)", "job role (role)", "job role (job)", "job title (job)", "job description (role)", "job description (job)", "job title (job title)", "job role (job role)", "job description (job description)"},
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
    "emergency_address": {"emergency_address", "emergency address", "emergency location","emergency_location", "emergency_residence", "emergency residence","emergency home address", "emergency_home_address","emergency contact address", "emergency_contact_address",  "emergency_address(location)"},
    "phone": {"phone", "contact_number", "mobile", "cell", "telephone", "phone number", "contact number", "mobile number", "cell number", "telephone number"},
    "company": {"company", "employer", "organization", "company name", "employer name", "organization name"},
    # For NextOfKin and EmergencyContact:
    "emergency_phone": {"emergency phone", "emergency_phone", "emergency number", "emergency_number", "emergency mobile", "emergency_mobile", "emergency cell", "emergency_cell", "emergency telephone", "emergency_telephone"},
    "nok_phone": {"nok phone", "nok_phone", "nok number", "nok_number", "nok mobile", "nok_mobile", "nok cell", "nok_cell", "nok telephone", "nok_telephone"},
    "nok_address": {"nok_address", "nok address", "nok location","nok_location", "nok_residence", "nok residence","nok home address", "nok_home_address","nok contact address", "nok_contact_address",  "nok_address(location)"},
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
    "middle name": "middle_name",
    "middlename": "middle_name",
    "last name": "last_name",
    "lastname": "last_name",
    "surname": "last_name",
    "title": "title",
    "sex": "gender",
    "gender": "gender",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
    "marital status": "marital_status",
    "email": "email",
    "contact": "contact_info",
    "phone": "contact_info",
    "hire date": "hire_date",
    "termination date": "termination_date",
    "employee type": "employee_type",  # For mapping to the EmployeeType table.
    "rank": "rank",  # For mapping to the Rank table.
    "assigned_dept": "department",  # For mapping to the Department table.
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

# Constants for Random Username and Password Generation
CHARACTER_SET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()"

def generate_random_string(length: int) -> str:
    return ''.join(secrets.choice(CHARACTER_SET) for _ in range(length))

class BulkInsertService:
    def __init__(self):
        # map model names to classes and expected fields
        # Mapping from model names to model classes.
        self.model_classes = {
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
        # self.model_field_map = {
        #     "employee": {"email", "first_name", "last_name", "date_of_birth", "hire_date", "department",
        #                  "rank", "employee type", "employment type", "salary", "role", "termination_date"},
        #     # Add other model field sets for dynamic sheets here.
        # }
        self.model_field_map: Dict[str, set] = {
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
    
    # ---------------------- Helper Functions ----------------------
    def _read_file(self, file: UploadFile) -> Dict[str, pd.DataFrame]:
        """
        Validates file extension and reads CSV/Excel data returning a dictionary of sheetname: DataFrame.
        """
        if not allowed_file(file.filename):
            raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed.")
        try:
            contents = file.file.read()
            file_stream = io.BytesIO(contents)
            if file.filename.lower().endswith("csv"):
                df = pd.read_csv(file_stream)
                return {"default": df}
            else:
                return pd.read_excel(file_stream, sheet_name=None)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

    def _prepare_employee_data(self, row_data: dict, organization_id: str, org, db: Session) -> Tuple[dict, Any, Any]:
        """
        Process and sanitize row data from employee sheet, and prepare model_data, role and salary.
        """
        expected_fields = self.model_field_map["employee"]
        model_data = {}
        extra_data = {}
        transient_role_id = None
        salary_value = None

        # Process each field using fuzzy matching.
        for col_name, val in row_data.items():
            concept = find_standard_concept(col_name)
            # Map concept to expected field if matching.
            for field in expected_fields:
                if normalize_column_name(field) == normalize_column_name(concept):
                    concept = field
                    break
            if concept in expected_fields and val is not None:
                model_data[concept] = val
            else:
                if any(x in concept for x in ["address", "phone", "contact", "gps"]):
                    extra_data[concept] = val

        if extra_data:
            model_data["contact_info"] = extra_data

        # Convert date fields.
        for dcol in ["date_of_birth", "hire_date", "termination_date"]:
            if dcol in model_data and model_data[dcol] is not None:
                model_data[dcol] = parse_date_value(model_data[dcol])

        # Add organization reference.
        model_data["organization_id"] = organization_id

        # Process related fields (Branch, Department, Rank, Employee Type, Role)
        # – Branch & Department:
        branch_id = None
        branch_key = next((k for k in row_data if find_standard_concept(k).lower() == "branch"), None)
        if branch_key:
            branch_val = row_data.get(branch_key)
            if branch_val:
                branch_val = str(branch_val).strip()
                branch_location = str(row_data.get("location", branch_val)).strip()
                if org.nature.strip().lower() == "single managed":
                    raise HTTPException(
                        status_code=400,
                        detail=f"Organization '{org.name}' is single managed; branch data is not allowed."
                    )
                # Process branch record.
                from Models.Tenants.organization import Branch
                branch_id = self.process_related_field(db, organization_id, branch_val, Branch, "name",
                                                        {"location": branch_location, "manager_id": None})
        if "department" in model_data and model_data["department"]:
            dept_val = str(model_data["department"]).strip()
            defaults = {"branch_id": branch_id} if branch_id else {}
            dept_id = self.process_related_field(db, organization_id, dept_val, Department, "name", defaults)
            model_data["department_id"] = dept_id
            model_data.pop("department", None)

        # – Rank:
        if "rank" in model_data and model_data["rank"]:
            rank_val = str(model_data["rank"]).strip()
            rank_id = self.process_related_field(db, organization_id, rank_val, Rank, "name",
                                                   {"min_salary": 0, "max_salary": None, "currency": "GHS"})
            model_data["rank_id"] = rank_id
            model_data.pop("rank", None)

        # – Employee Type:
        if "employee type" in model_data and model_data["employee type"]:
            et_val = str(model_data["employee type"]).strip()
            et_id = self.process_related_field(db, organization_id, et_val, EmployeeType, "type_code", {})
            model_data["employee_type_id"] = et_id
            model_data.pop("employee type", None)
        elif "employment type" in model_data and model_data["employment type"]:
            et_val = str(model_data["employment type"]).strip()
            et_id = self.process_related_field(db, organization_id, et_val, EmployeeType, "type_code", {})
            model_data["employee_type_id"] = et_id
            model_data.pop("employment type", None)

        # – Role:
        if "role" in model_data and model_data["role"]:
            role_val = str(model_data["role"]).strip()
            existing_role = db.query(Role).filter(
                Role.name.ilike(role_val),
                Role.organization_id == organization_id
            ).first()
            if not existing_role:
                default_perms = {"view": "own", "edit": "own"} if role_val.lower() == "staff" else {}
                new_role = Role(name=role_val, permissions=default_perms, organization_id=organization_id)
                db.add(new_role)
                db.commit()
                db.refresh(new_role)
                transient_role_id = str(new_role.id)
            else:
                transient_role_id = str(existing_role.id)
            model_data.pop("role", None)
        else:
            transient_role_id = self.get_or_create_default_role(db, organization_id)

        # – Salary:
        if "salary" in model_data and model_data["salary"]:
            try:
                salary_value = float(model_data["salary"])
            except Exception:
                salary_value = None
            model_data.pop("salary", None)

        return model_data, transient_role_id, salary_value

    def _determine_model_choice(self, df: pd.DataFrame) -> Tuple[str, set]:
        """
        Determines best matching model choice for a given dataframe based on column overlap.
        Defaults to 'dynamic' if no strong match is found.
        """
        max_match = 0
        model_choice = "dynamic"
        expected_fields = set()
        for model, fields in self.model_field_map.items():
            overlap = len(set(df.columns).intersection(fields))
            if overlap > max_match:
                max_match = overlap
                model_choice = model
                expected_fields = fields
        return model_choice, expected_fields

    def _prepare_dynamic_data(self, row_data: dict, expected_fields: set) -> dict:
        """
        Prepares model data for dynamic (non-employee) records.
        """
        model_data = {}
        for col_name, val in row_data.items():
            concept = find_standard_concept(col_name)
            if concept in expected_fields and val is not None:
                # Process dates.
                if concept in {"start_date", "end_date", "payment_date", "hire_date", "termination_date"}:
                    model_data[concept] = parse_date_value(val)
                # Process numeric fields.
                elif concept in {"year_obtained", "year_of_experience"}:
                    try:
                        model_data[concept] = int(val)
                    except Exception:
                        model_data[concept] = None
                else:
                    model_data[concept] = val
        return model_data

    # The following functions are placeholders that should exist in your codebase.
    def get_primary_logo(self, logos: dict) -> str:
        # Return the primary logo URL given organization logos.
        return logos.get("primary", "https://example.com/default_logo.png")

    def process_related_field(self, db: Session, organization_id: str, field_value: str,
                              ModelClass: Any, lookup_field: str,
                              defaults: dict) -> Any:
        """
        Lookup or create a related record (e.g., Branch, Department, Rank, EmployeeType) and return its id.
        """
        instance = db.query(ModelClass).filter(
            getattr(ModelClass, lookup_field).ilike(field_value),
            ModelClass.organization_id == organization_id
        ).first()
        if not instance:
            instance = ModelClass(**{lookup_field: field_value, **defaults, "organization_id": organization_id})
            db.add(instance)
            db.commit()
            db.refresh(instance)
        return instance.id

    def get_or_create_default_role(self, db: Session, organization_id: str) -> str:
        """
        Retrieve a default role id for the organization or create one if not exists.
        """
        default_role = db.query(Role).filter(
            Role.name == "default",
            Role.organization_id == organization_id
        ).first()
        if not default_role:
            default_role = Role(name="default", permissions={}, organization_id=organization_id)
            db.add(default_role)
            db.commit()
            db.refresh(default_role)
        return str(default_role.id)

    def build_account_email_html(self, model_data: dict, org_acronym: str, logo_url: str,
                                 login_href: str, transient_pwd: str) -> str:
        """
        Build and return HTML content for the account creation email.
        """
        # Construct email HTML using the provided data.
        html_content = f"""
        <html>
          <body>
            <img src="{logo_url}" alt="{org_acronym} logo" />
            <h3>Your Account has been Created</h3>
            <p>You can login at <a href="{login_href}">{login_href}</a></p>
            <p>Your temporary password is: <strong>{transient_pwd}</strong></p>
          </body>
        </html>
        """
        return html_content

    def bulk_insert_crud(self, organization_id: str, file: UploadFile,
                         background_tasks: BackgroundTasks, db: Session) -> dict:
        # ---------------------- STEP 1: Validate and Read File ----------------------
        sheets = self._read_file(file)
        if not sheets:
            raise HTTPException(status_code=400, detail="No sheets found in file.")

        # ---------------------- STEP 2: Retrieve Organization ----------------------
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        logo_url = get_primary_logo(org.logos or {})
        org_acronym = get_organization_acronym(org.name)
        login_href = f"{org.access_url}/signin" if org.access_url else "https://example.com/login"

        # Initialize response data containers.
        success_records: List[Dict] = []
        error_records: List[Dict] = []
        failed_rows_by_sheet: Dict[str, List[int]] = {}
        employee_map: Dict[str, Any] = {}   # email (lowercase) -> employee_id
        employee_list: List[Any] = []         # preserve insertion order

        # ---------------------- STEP 3: Process Employee Records ----------------------
        # Sort sheets: process those with maximum overlap with employee fields first.
        ordered_sheets = sorted(
            sheets.items(),
            key=lambda item: len(set(item[1].columns.str.lower()).intersection(self.model_field_map["employee"])),
            reverse=True
        )

        total_employee_rows = 0
        for sheet_name, df in ordered_sheets:
            sheet_id = sheet_name.strip().lower()
            # Process only if this sheet appears to contain employee data.
            if sheet_id in {"employee", "employees"} or \
               len(set(df.columns.str.lower()).intersection(self.model_field_map["employee"])) >= 5:
                df.columns = [col.strip().lower() for col in df.columns]
                total_employee_rows += len(df)
                for idx, row in df.iterrows():
                    row_data = sanitize_row_data(dict(row))
                    try:
                        model_data, transient_role_id, salary_value = self._prepare_employee_data(
                            row_data, organization_id, org, db
                        )
                        # Generate a random password.
                        transient_pwd = generate_random_string(6)

                        # Build and insert Employee record.
                        record = Employee(**model_data)
                        if transient_role_id:
                            setattr(record, "_role_id", transient_role_id)
                            setattr(record, "_plain_password", transient_pwd)
                        db.add(record)
                        db.flush()  # Get primary key

                        # Update mapping using lowercase email.
                        if "email" in model_data and model_data["email"]:
                            email_lower = model_data["email"].lower()
                            employee_map[email_lower] = record.id
                            employee_list.append(record.id)

                        # Create salary payment record if applicable.
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
                            "row_index": idx,
                            "model": "employee",
                            "data": row_data
                        })

                        # Send email notification asynchronously.
                        if "email" in model_data and model_data["email"]:
                            try:
                                email_service = EmailService()
                                email_body = self.build_account_email_html(
                                    model_data, org_acronym, logo_url, login_href, transient_pwd
                                )
                                background_tasks.add_task(
                                    email_service.send_html_email,
                                    background_tasks,
                                    [model_data["email"]],
                                    "Account Created Successfully",
                                    email_body
                                )
                            except Exception as email_exc:
                                # Log but do not interrupt processing.
                                print(f"[WARN] Failed to send email for row {idx}: {email_exc}")

                    except Exception as e:
                        db.rollback()
                        error_records.append({
                            "sheet": sheet_name,
                            "row_index": idx,
                            "error": str(e),
                            "data": row_data
                        })
                        failed_rows_by_sheet.setdefault(sheet_name, []).append(idx)

        # ---------------------- STEP 4: Process Additional (Dynamic) Sheets ----------------------
        if employee_map:
            for sheet_name, df in sheets.items():
                # Skip sheets already processed as employee data.
                sheet_id = sheet_name.strip().lower()
                if sheet_id in {"employee", "employees"} or \
                   len(set(df.columns.str.lower()).intersection(self.model_field_map["employee"])) >= 5:
                    continue

                df.columns = [col.strip().lower() for col in df.columns]
                # Determine the best matching model based on column overlap.
                model_choice, expected_fields = self._determine_model_choice(df)
                for idx, row in df.iterrows():
                    row_data = sanitize_row_data(dict(row))
                    try:
                        model_data = self._prepare_dynamic_data(row_data, expected_fields)
                        # Try to link the record to an employee via email; if not available, assume order mapping.
                        if "email" in row_data and row_data["email"]:
                            emp_id = employee_map.get(row_data["email"].lower())
                            if emp_id:
                                model_data["employee_id"] = emp_id
                        elif "employee_id" not in model_data and idx < len(employee_list):
                            model_data["employee_id"] = employee_list[idx]

                        # Attach organization_id if applicable.
                        ModelClass = self.model_classes.get(model_choice, None)
                        if ModelClass and hasattr(ModelClass, "__table__") and "organization_id" in ModelClass.__table__.columns:
                            model_data["organization_id"] = organization_id

                        # Create and insert related record.
                        if ModelClass:
                            record = ModelClass(**model_data)
                        else:
                            # Fallback to dynamic data if no matching model was found.
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
                            "row_index": idx,
                            "model": model_choice,
                            "data": row_data
                        })
                    except Exception as e:
                        db.rollback()
                        error_records.append({
                            "sheet": sheet_name,
                            "row_index": idx,
                            "error": str(e),
                            "data": row_data
                        })
                        failed_rows_by_sheet.setdefault(sheet_name, []).append(idx)
        else:
            print("No employee records processed; skipping processing of related sheets.")

        # ---------------------- STEP 5: Log Errors if Present ----------------------
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
        print(f"Success count: {success_count}")
        # Filter out errors related to employee records.
        error_records = [r for r in error_records if r["model"] == "employee"]
        failure_count = len(error_records)

        print(f"Failure count: {failure_count}")
        print("error_records: ", error_records)
        print("success_records: ", success_records)

        # Compose message based on results.
        if success_count and not failure_count:
            msg = "Registered users should check their emails for access to the system."
        elif success_count and failure_count:
            msg = (f"Employees should check their emails for access to the system; however, some records "
                   "failed. Please review the failed records (see details below) and try manual insertion.\n**************************************************\n\t\tDetails\n**************************************************")
            msg += "\n".join([f"Sheet: {r['sheet']}, Row: {r['row_index']}, Error: {r['error']}" for r in failed_rows_by_sheet.values()])
        else:
            msg = "All records failed. Please review the errors and try again or register the records manually."

        return {
            "detail": "Bulk upload processed.",
            "total_employee_rows": total_rows,
            "successful_inserts": len(success_records),
            "failed_inserts": failure_count,
            "failed_rows_by_sheet": failed_rows_by_sheet,
            "message": msg
        }

    