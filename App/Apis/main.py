from datetime import date, datetime
import re
from passlib.context import CryptContext
import secrets
from dateutil.relativedelta import relativedelta
from fastapi import FastAPI, APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request, status, UploadFile, File, Form
from pydantic import EmailStr
from sqlalchemy.orm import Session
from uuid import UUID 
from typing import Dict, List, Optional
from Crud.auth import get_current_user_for_others
from Service.email_service import EmailService, build_account_email_html
from Service.custom_email_service import EmailService as CustomEmailService
from Service.custom_email_settings import DEFAULT_EMAIL_SETTINGS
from Service.email_config_service import EmailConfigService
from Schemas.schemas import TenantEmailSettings
# from email_service import EmailService
# from 
from Service.storage_service import BaseStorage
import json
from database.db_session import get_db  # Your database session dependency
from Crud.crud import CRUDBase  # Generic CRUD class
from Crud.branch import *
from Crud.department import *
from Models.Tenants.organization import *  # Import your models
from Models.Tenants.role import Role  # Import your models
from Models.models import ( User,  Employee, AcademicQualification,
                        ProfessionalQualification, EmploymentHistory,
                        EmergencyContact, NextOfKin, FileStorage, AuditLog,
                        SystemSetting, Dashboard, Department)  # Import your models
from Schemas.schemas import (OrganizationCreateSchema, OrganizationSchema,
                             BranchCreate, BranchOut, BranchUpdate,
                             DepartmentCreate, DepartmentUpdate, DepartmentOut,

                            
                            RoleCreateSchema,
                         RoleSchema, StaffOption, UserCreateSchema, UserSchema, TenancyCreateSchema,
                         TenancySchema, TermsAndConditionsSchema, BillSchema,
                         PaymentSchema, EmployeeCreateSchema, EmployeeSchema,
                         AcademicQualificationCreateSchema, AcademicQualificationSchema,
                         ProfessionalQualificationCreateSchema, ProfessionalQualificationSchema,
                         EmploymentHistoryCreateSchema, EmploymentHistorySchema,
                         EmergencyContactCreateSchema, EmergencyContactSchema,
                         NextOfKinCreateSchema, NextOfKinSchema, FileStorageSchema,
                         AuditLogSchema, SystemSettingSchema, DashboardSchema)
from Service.gcs_service import GoogleCloudStorage
from Utils.util import   extract_items, get_create_user_url, get_organization_acronym  # Import your utility classes
import json
from Service.gcs_service import GoogleCloudStorage
from Utils.config import ProductionConfig, get_config
from Service.service import upload_to_google_cloud
import logging
from Service.file_service import upload_file
from Utils.file_handler import get_gcs_client
from Utils.serialize_4_json import serialize_for_json
from Utils.storage_utils import get_storage_service
from Utils.sms_utils import get_sms_service
from Utils.security import Security
from fastapi_mail.errors import ConnectionErrors




# Create the FastAPI app
app = APIRouter()

config = ProductionConfig()  # Load the development configuration


security = Security(config.SECRET_KEY, config.ALGORITHM, config.ACCESS_TOKEN_EXPIRE_MINUTES)


TITLE_PATTERN = re.compile(r'^(Prof\.|Dr\.|Mr\.|Mrs\.|Ms\.|PhD\.|Ing\.|Rev\.)\s+', re.IGNORECASE)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

gcs= GoogleCloudStorage(bucket_name=config.BUCKET_NAME)  # Replace with your actual bucket name

current_date = date.today()
next_year = current_date + relativedelta(years=5)

# Instantiate generic CRUD classes
organization_crud = CRUDBase(Organization)
role_crud = CRUDBase(Role)
user_crud = CRUDBase(User)
tenancy_crud = CRUDBase(Tenancy)
employee_crud = CRUDBase(Employee)
academic_qualification_crud = CRUDBase(AcademicQualification)
professional_qualification_crud = CRUDBase(ProfessionalQualification)
employment_history_crud = CRUDBase(EmploymentHistory)
emergency_contact_crud = CRUDBase(EmergencyContact)
next_of_kin_crud = CRUDBase(NextOfKin)
system_setting_crud = CRUDBase(SystemSetting)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")




@app.get(
    "/{org_id}/departments/{dept_id}/head",
    response_model=StaffOption,
    summary="Get Head‑of‑Department basic info",
    responses={
        403: {"description": "Forbidden – user not in this org"},
        404: {"description": "Dept not found or has no head assigned"},
    },
)
def get_department_head(
    org_id: UUID,
    dept_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_for_others),
):
    # — Authorization
    if current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission for this organization.",
        )

    # — Fetch Department & ensure it belongs to this org
    dept = (
        db.query(Department)
        .filter(
            Department.id == dept_id,
            Department.organization_id == org_id,
        )
        .first()
    )
    if not dept or not dept.department_head_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found or no head assigned.",
        )

    # — Fetch Employee (only the fields we need)
    emp: Optional[Employee] = (
        db.query(
            Employee.id,
            Employee.title,
            Employee.first_name,
            Employee.middle_name,
            Employee.last_name,
        )
        .filter(
            Employee.id == dept.department_head_id,
            Employee.organization_id == org_id,
            Employee.is_active == True,
        )
        .first()
    )
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Head‑of‑department record not found or inactive.",
        )

    # — Respond using StaffOption schema
    return StaffOption(
        id=emp.id,
        title=emp.title,
        first_name=emp.first_name,
        middle_name=emp.middle_name,
        last_name=emp.last_name,
    )




@app.get("/slug/{slug}")
def get_org_by_slug(slug: str, db: Session = Depends(get_db)):
    # Here we assume that access_url is stored as "https://gi-kace-solutions.onrender.com/{slug}"
    # One option is to filter using a LIKE condition:
    org = db.query(Organization).filter(Organization.access_url.ilike(f"%/{slug}")).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

@app.get("/create-url", summary="Fetch create user submit button request API URL")
async def get_user_create_url(request: Request):
    """
    Returns the backend host URL with '/api/users/create' appended.
    """
    url = get_create_user_url(request)
    return {"user_create_url": url}


@app.post("/create-form/",  response_model=OrganizationSchema, status_code=status.HTTP_201_CREATED)
async def create_organization_form(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    organizational_email: str = Form(...),
    country: str = Form(...),
    type: str = Form(...),
    nature: str = Form(...),
    employee_range: str = Form(...),
    subscription_plan: Optional[str] = Form("Basic"),
    logos: Optional[List[UploadFile]] = File(None),  # Organization logos
    user_images: Optional[List[UploadFile]] = File(None),  # User profile images
    tenancies: Optional[str] = Form(json.dumps([
            {
                "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "start_date": "2025-01-01",
                "billing_cycle": "Monthly",
                "terms_and_conditions_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "terms_and_conditions": [
                    {
                        "title": "Default Terms",
                        "content": {"agreement": "Sample agreement text"},
                        "version": "1.0",
                        "is_active": True
                    }
                ]
            }
        ])),  # JSON string for tenancies
    roles: Optional[str] = File(json.dumps([
        {
        "name": "Admin",
        "permissions": [
            "employee:create",
            "employee:read",
            "employee:update",
            "employee:delete",
            "role:manage",
            "user:assignRole",
            "audit:read",
            "organization:update",
            "hr:dashboard",
            "admin:dashboard",
            "hr:dashboard:settings",
        ],
      "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    },
    {
        "name": "HR", 
        "permissions": [
            "employee:create",
            "employee:create:dashboard",
            "employee:read:dashboard",
            "employee:update:dashboard",
            "employee:read",
            "employee:update",
            "employee:delete",
            "employee:archive",
            "employee:transfer",
            "attendance:record",
            "role:manage",
            "user:assignRole",
            "audit:read",
            "organization:create",
            "organization:update",
            "organization:read",
            "hr:dashboard",
            "hr:dashboard:read",
        ],
        "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" 
        },
        {
        "name": "Branch Manager",
            "permissions": [
                "employee:read",
                "employee:update",
                "branch:manager:dashboard",
                "branch:manage",
            ],
        "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" 
        }
    ])),  # JSON string for roles
    employees: Optional[str] = Form(json.dumps([
        {
        "title": "Mr",
        "first_name": "Sam",
        "middle_name":"Kwaku",
        "last_name": "Badu",
        "date_of_birth": "1980-01-01",
        "email": "vboat54@gmail.com",
        "contact_info": {},
        "hire_date": str(current_date),
        "termination_date": str(next_year),
        "custom_data": {
            "has_previous_name": True,
            "previous_name": "Sam Kwaku Boateng",
            "Nationality": "Ghanaian",
            "National_ID": "GHA123456789",
        },
        "staff_id": "1234567890",
        "profile_image_path": "google.com/sam",
        "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    },
    # {
    #     "title": "Mrs",
    #     "first_name": "Mary",
    #     "middle_name":"",
    #     "last_name": "Adwubi",
    #     "date_of_birth": "1980-01-01",
    #     "email": "mary@example.com",
    #     "contact_info": {},
    #     "hire_date": str(current_date),
    #     "termination_date": str(next_year),
    #     "custom_data": {
    #         "has_previous_name": False,
    #         "previous_name": "",
    #         "Nationality": "Ghanaian",
    #         "National_ID": "GHA987654321",
    #     },
    #     "profile_image_path": "google.com/mary",
    #     "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"

    # }
    
    ])),
    users: Optional[str] = Form(json.dumps([
                {
                    "username": "",
                    "email": "vboat54@gmail.com",   
                    "hashed_password": "",
                    "role_id": "123e4567-e89b-12d3-a456-426614174000",
                    "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", 
                    "image_path": "google.com/sam"
                    
                },
                # {
                #      "username": "",
                #     "email": "mary@example.com",   
                #     "hashed_password": "",
                #     "role_id": "123e4567-e89b-12d3-a456-426614174000",
                #     "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", 
                #     "image_path": "google.com/mary"

                # }

            ])),  # JSON string for users
    settings: Optional[str] = Form(json.dumps([
        {
            "setting_name": "dashboard_theme",
            "setting_value": {         "color": "blue",         "font_size": "12px"       } ,
            "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        }
        ])),  # JSON string for settings
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage_service),
    sms_svc: object = Depends(get_sms_service),
        # email_smtp_config: dict = Depends(get_smtp_config),
    config: ProductionConfig = Depends(get_config),  # Inject config
    ):
    

    try:
        bucket_name = config.BUCKET_NAME

        # Parse JSON strings for nested fields
        tenancies_data = json.loads(tenancies) if tenancies else []
        roles_data = json.loads(roles) if roles else []
        employee_data = json.loads(employees) if employees else []
        users_data = json.loads(users) if users else []
        settings_data = json.loads(settings) if settings else []


        print(f"""tenancies_data: {tenancies_data}\n
              roles_data: {roles_data}\n
              employee_data: {employee_data}\n
              users_data: {users_data}\n
              settings_data: {settings_data}\n
            """)
       

         # Validate parsed JSON data
        for field_name, field_value in {
            "tenancies": tenancies_data,
            "roles": roles_data,
            "employees": employee_data,
            "users": users_data,
            "settings": settings_data,
        }.items():
            if not isinstance(field_value, list):
                raise HTTPException(status_code=400, detail=f"Invalid JSON format for '{field_name}'")

        # Initialize Google Cloud Storage
        gcs_client = GoogleCloudStorage(bucket_name)

       
        # logo_urls={}
        # # Process uploaded files for logos
        # if logos:
        #     logo_files = [{"filename": file.filename, "content": await file.read()} for file in logos]
          
        #     logo_urls = gcs_client.upload_to_gcs(files=logo_files, folder=f"organizations/{get_organization_acronym(name)}/logos") or {}

        # UPLOAD logos
        logo_urls = {}
        print("logos: ", logos)
        if logos:
            files = [
                {"filename": f.filename, "content": await f.read(), "content_type": f.content_type}
                for f in logos
            ]
            logo_urls = storage.upload(files, f"organizations/{get_organization_acronym(name)}/logos")      

        # Process uploaded files for user profile images
        # image_urls={}
        # if user_images:
        #     if len(user_images) != len(users_data):
        #         raise HTTPException(
        #             status_code=400,
        #             detail="The number of user images does not match the number of users."
        #         )

        #     user_files = [{"filename": file.filename, "content": await file.read()} for file in user_images]
        #     image_urls = gcs_client.upload_to_gcs(files=user_files, folder=f"organizations/{get_organization_acronym(name)}/user_profiles") or {}

          # UPLOAD user images
        image_urls = {}
        if user_images:
            if len(user_images) != len(users_data):
                raise HTTPException(
                    status_code=400,
                    detail="The number of user images does not match the number of users."
                )
            user_files = [
                {"filename": f.filename, "content": await f.read(), "content_type": f.content_type}
                for f in user_images
            ]
            image_urls = storage.upload(user_files, f"organizations/{get_organization_acronym(name)}/user_profiles") 


             # Attach image paths to users
            for i, user in enumerate(users_data):
                user["image_path"] = image_urls.get(user_files[i]["filename"], "https://example.com/default-profile-image.png")

            #Attach image paths to employees
            for i, employee in enumerate(employee_data):
                employee["profile_image_path"] = image_urls.get(user_files[i]["filename"],  "https://example.com/default-profile-image.png")
       
       # Fallback for Default logos and images
        logo_urls = logo_urls or {
            "primary": "https://example.com/default-logo-primary.png",
            "secondary": "https://example.com/default-logo-secondary.png",
        }

        # Fallback for default image paths if upload_to_gcs returned empty
        for user in users_data:
            user.setdefault("image_path", "https://example.com/default-profile-image.png")
        
        for employee in employee_data:
            employee.setdefault("profile_image_path", "https://example.com/default-profile-image.png")


        # Prepare organization schema
        organization_data = OrganizationCreateSchema(
            name=name,
            org_email=organizational_email,
            country=country,
            type=type,
            nature=nature,
            employee_range=employee_range,
            access_url="",
            subscription_plan=subscription_plan,
            image_path=image_urls,
            logos=logo_urls,  # Placeholder for logos URLs
            tenancies=tenancies_data,
            roles=roles_data, 
            employees=employee_data,
            users=users_data,
            settings=settings_data,
        )

        
            
        # Call the CRUD function
        organization = await organization_crud.create_with_nested(
            background_tasks, db, obj_in=organization_data
        )

        # 4. Schedule SMS _here_, never in CRUD
        for emp in employee_data:
            ci = emp.get("contact_info", {})
            # if someone accidentally sent a JSON‐string in contact_info, try decode
            if isinstance(ci, str):
                try:
                    ci = json.loads(ci)
                except:
                    continue
            if not isinstance(ci, dict):
                continue

            phone = ci.get("phone".lower()) or ci.get("mobile".lower()) or ci.get("contact".lower()) or ci.get("phone number".lower()) or \
                    ci.get("phone_number".lower()) or ci.get("mobile number".lower()) or ci.get("mobile_number".lower()) or \
                    ci.get("contact number".lower()) or ci.get("contact_number".lower())
            if not phone:
                continue

            background_tasks.add_task(
                sms_svc.send,
                phone,
                "org_signup",
                {"first_name": emp.get("first_name", ""), "org_name": name}
            )

        return organization
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON format in 'users' or 'tenancies'")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# Constants for Random Username and Password Generation
CHARACTER_SET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ012345679"
USERNAME_LENGTH = 8
PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
        return pwd_context.hash(password)



# Helper function to generate random string
def generate_random_string(length: int) -> str:
    return ''.join(secrets.choice(CHARACTER_SET) for _ in range(length))

def get_primary_logo(logos: dict) -> str:
    """Return the first URL from the logos dict if available, else a default."""
    if logos and isinstance(logos, dict):
        # Simply return the first value.
        for key, url in logos.items():
            if url:
                return url
    return "https://example.com/default-logo.png"

@app.post("/", response_model=OrganizationSchema, status_code=status.HTTP_201_CREATED)
async def create_organization(
    
    background_tasks: BackgroundTasks,
    phone_number: str = Form(...),
    contact_email: EmailStr = Form(...),
    contact_person: str = Form(...),
    subscription_plan: str = Form("Basic"),
    # employee_count: str = Form(...),
    domain: str = Form(...),
    organization_nature: str = Form(...),
    organization_email: EmailStr = Form(...),
    organization_name: str = Form(...),
    country: str = Form(...),
    org_type: str = Form(...),  # e.g., Private, Government, Public, NGO
    employee_range: str = Form(...),  # e.g., "0-10"
    organization_settings: str = Form(None),  # JSON string containing custom settings
    logos: List[UploadFile] = File(None),
    storage: BaseStorage = Depends(get_storage_service),
    db: Session = Depends(get_db),
):
    """
    Create a new organization, upload logos, create a default Admin role,
    and create a User account for the contact person with a generated password.
    """
    # Validate subscription_plan
    if subscription_plan not in ["Basic", "Premium"]:
        raise HTTPException(status_code=400, detail="Invalid subscription plan.")

    # Check if organization name or email already exist
    existing_org = db.query(Organization).filter(
        (Organization.name == organization_name) | (Organization.org_email == organization_email)
    ).first()
    if existing_org:
        raise HTTPException(status_code=400, detail="Organization name or email already exists.")

    # Upload logo files to external storage and store URLs
    logo_urls = {}
    if logos:
        files_payload = []
        for f in logos:
            content = await f.read()
            files_payload.append({
                "filename": f.filename,
                "content": content,
                "content_type": f.content_type,
            })
        folder_path = f"organizations/{get_organization_acronym(organization_name)}/logos"
        logo_urls = storage.upload(files_payload, folder_path)
    
    # domain = f"https://{domain.strip()}" if not domain.startswith("http") else domain.strip()
    # if not domain.endswith("/"):
    #     domain += "/"
    
    ab = get_organization_acronym(organization_name).lower()
    print("\n\nabbr.: ", ab)
    slug = f"{ab}-{generate_random_string(8)}"
    # obj_data["access_url"] = f"http://localhost:8000/{slug}"

    # domain = f"f"{settings.TENANT_URL}/{slug}"

    domain = f"{config.TENANT_URL}/{slug}" if config.TENANT_URL else ""

    # Create organization record
    new_org = Organization(
        name=organization_name.strip(),
        org_email=organization_email,
        country=country.strip(),
        type=org_type.strip(),
        nature=organization_nature.strip(),
        employee_range=employee_range.strip(),
        logos=logo_urls,  # Store returned URLs
        access_url=domain,
        subscription_plan=subscription_plan,
        is_active=True,
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    # Handle organization settings if provided - save to SystemSetting table
    if organization_settings:
        try:
            settings_data = json.loads(organization_settings)
            email_config_service = EmailConfigService(db, schema_based=False)
            
            # Extract email settings from the organization settings
            if "emailSettings" in settings_data:
                email_settings = settings_data["emailSettings"]
                # Create TenantEmailSettings object
                tenant_email_settings = TenantEmailSettings(
                    provider=email_settings.get("provider", "smtp"),
                    host=email_settings.get("host"),
                    port=email_settings.get("port", 587),
                    username=email_settings.get("username"),
                    password=email_settings.get("password"),
                    use_tls=email_settings.get("use_tls", True),
                    default_from=email_settings.get("default_from", organization_email),
                    logo_path=email_settings.get("logo_path"),
                    api_key=email_settings.get("api_key"),
                    templates_dir="templates/emails",
                    schema_based=False
                )
                # Store email settings in SystemSetting table
                email_config_service.create(new_org.id, tenant_email_settings)
                logger.info(f"Custom email settings saved to SystemSetting table for organization {new_org.id}")
                
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse organization settings: {e}")
            # Continue without custom settings - will use default email service

    default_perms = []
    # if role_val.lower() == "staff":
        # Locate the 'Employee' or 'staff' role configuration.
    role_config = next(
        (role_item for role_item in config.DEFAULT_ROLE_PERMISSIONS
        if ("Admin".lower() == role_item["name"].lower()) or ("Admin".lower() in role_item["name"].lower()) ),
        None
    )
    print("role_config: ", role_config)
    if role_config:
        default_perms = role_config.get("permissions", [])
        print("default_perms: ", default_perms)
    # Create a default Admin role for this organization
    admin_role = Role(
        name="Admin",
        permissions=default_perms,  # Full access
        organization_id=new_org.id,
    )
    db.add(admin_role)
    db.commit()
    db.refresh(admin_role)

    # Generate user account for contact person (organization administrator)
    username = contact_email
    plain_password = generate_random_string(6)
    hashed_pw = hash_password(plain_password)

    # 1) Extract title + clean name
    m = TITLE_PATTERN.match(contact_person.strip())
    if m:
        title = m.group(1).strip()
        name_body = contact_person[m.end():].strip()
    else:
        title = ""
        name_body = contact_person.strip()

    parts = name_body.split()
    first_name = parts[0]
    middle_name = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    last_name = parts[-1] if len(parts) > 1 else ""

    new_emp = Employee(
        title=title,
        first_name=first_name,
        middle_name=middle_name,  #" ".join(contact_person.split()[1:-1]) if len(contact_person.split()) > 2 else "",
        last_name=last_name,
        date_of_birth=None,  # Optional, can be added later
        email=contact_email,
        contact_info={"phone": phone_number},
        hire_date=datetime.now(),
        termination_date=datetime.now() + relativedelta(years=5),  # Default to 5 years
        custom_data={},  # Optional, can be added later
        organization_id=new_org.id,  # Associate with the new organization  
    )
    setattr(new_emp, '_role_id', admin_role.id)  # Set the role ID for the employee
    setattr(new_emp, "_plain_password", plain_password)
    # new_emp.organization_id = new_org.id  # Associate with the new organization
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)

    
    

    row_data = {
        "title":title,
        "first_name": first_name,
        "last_name": last_name,
        "email": contact_email,
        "org_name": organization_name.strip(),
    }
   

    try:
        # Use the first logo if multiple logos are provided
        logo_urls = {k: v for k, v in logo_urls.items() if v}  # Filter out empty URLs
        print(f"logo_urls: {logo_urls}")

        # logo = next(iter(logo_urls.values())) if len(logo_urls) > 1 else logo_urls


        logo = get_primary_logo(logo_urls)  # Get the primary logo URL
        
        image = gcs.extract_gcs_file_path(logo) if logo else "https://example.com/default-logo.png"
        print(f"logo: {logo}")
        print(f"final image: {logo}")
        # Use the first logo URL as the logo for the email
        # if isinstance(logo, dict):
        #     logo = next(iter(logo.values()))
        # elif isinstance(logo, list):
        #     logo = logo[0] if logo else "https://example.com/default-logo.png"
        # else:
        #     logo = logo or "https://example.com/default-logo.png"
        # # Ensure logo is a valid URL string
        # if not isinstance(logo, str):
        #     logo = "https://example.com/default-logo.png"

        # Build the email body using the utility function
        
        print(f"image: {extract_items(image)}")
        
        # Try to use custom email service if organization has custom settings, otherwise use default
        try:
            # Check if organization has custom email settings in SystemSetting table
            email_config_service = EmailConfigService(db, schema_based=False)
            custom_email_settings = email_config_service.read(new_org.id)
            
            if custom_email_settings:
                # Use custom email service
                custom_email_service = CustomEmailService(
                    tenant_id=str(new_org.id),
                    db=db,
                    default_settings=DEFAULT_EMAIL_SETTINGS
                )
                
                # Build email context for organization_created.html template
                email_context = {
                    "organization_name": organization_name,
                    "employee_name": f"{title} {first_name} {last_name}".strip(),
                    "user_avatar": "👤",  # Default avatar emoji
                    "username": contact_email,
                    "password": plain_password,
                    "login_url": domain + "/signin"
                }
                
                # Send email using custom service with template
                custom_email_service.send_email(
                    to=[contact_email],
                    subject=f"Welcome to {organization_name} - Your Account is Ready",
                    template_name="organization_created.html",
                    context=email_context
                )
                logger.info("Email sent using custom email service from SystemSetting table")
            else:
                # Use default email service with template
                email_service = EmailService()
                template_data = {
                    "organization_name": organization_name,
                    "employee_name": f"{title} {first_name} {last_name}".strip(),
                    "user_avatar": "👤",  # Default avatar emoji
                    "username": contact_email,
                    "password": plain_password,
                    "login_url": domain + "/signin"
                }
                await email_service.send_email(
                    background_tasks, 
                    recipients=[contact_email], 
                    subject=f"Welcome to {organization_name} - Your Account is Ready",
                    template_name="organization_created.html",
                    template_data=template_data
                )
                logger.info("Email sent using default email service with template")
                
        except Exception as email_error:
            logger.error(f"Custom email service failed, falling back to default: {email_error}")
            # Fallback to default email service with template
            email_service = EmailService()
            template_data = {
                "organization_name": organization_name,
                "employee_name": f"{title} {first_name} {last_name}".strip(),
                "user_avatar": "👤",  # Default avatar emoji
                "username": contact_email,
                "password": plain_password,
                "login_url": domain + "/signin"
            }
            await email_service.send_email(
                background_tasks, 
                recipients=[contact_email], 
                subject=f"Welcome to {organization_name} - Your Account is Ready",
                template_name="organization_created.html",
                template_data=template_data
            )
    except Exception as conn_exc:
        # extremely unlikely, since send_email just schedules a task,
        # but you could handle missing config here if you want.
        raise HTTPException(
            status_code=500,
            detail="Organization created, but email service not configured."
        ) from conn_exc

    return new_org


@app.get("/", response_model=List[OrganizationSchema])
async def get_all_organizations(
    db: Session = Depends(get_db)
):
    """
    Fetch all active organizations.
    """
    orgs = db.query(Organization).filter(Organization.is_active == True).all()
    return orgs



















# @app.post("/new/", response_model=OrganizationSchema, status_code=status.HTTP_201_CREATED)
# async def create_organization_endpoint(
#     background_tasks: BackgroundTasks,
#     organization: OrganizationCreateSchema,
#     db: Session = Depends(get_db),
    
# ):
#     """
#     Endpoint to create a new organization.
#     """
#     return await organization_crud.create_with_nested(background_tasks,db, obj_in=organization)




@app.get("/fetch/{organization_id}", response_model=OrganizationSchema)
def read_organization(organization_id: UUID, db: Session = Depends(get_db)):
    """
    Read an organization by ID
    """
    org = organization_crud.get(db, id=organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationSchema.model_validate(org)


@app.get("/batch/", response_model=List[OrganizationSchema])
def read_organizations(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """
    List all organizations
    """
    return organization_crud.get_multi(db, skip=skip, limit=limit)



######original
@app.patch("/v2/upd/{organization_id}", response_model=OrganizationSchema)
async def update_organization(
    organization_id: UUID,
    organization_update: Optional[str] = Form(...),  # Accept JSON string for updates
    logos: Optional[List[UploadFile]] = File(None),  # Upload files for logos
    user_images: Optional[List[UploadFile]] = File(None),  # Upload files for user profile images
    db: Session = Depends(get_db),
):
    """
    Update an organization by ID with support for partial updates, nested updates, and file uploads.
    """
    try:
        # Fetch the organization
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Parse the update payload
        if organization_update:
            try:
                organization_data = json.loads(organization_update)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail="Invalid JSON format for organization_update") from e
        else:
            organization_data = {}

        # Inject organization_id into payload for nested models
        organization_data["organization_id"] = str(organization_id)

        # Initialize Google Cloud Storage (or your storage provider)
        gcs_client = GoogleCloudStorage(config.BUCKET_NAME)

        # Process uploaded logos if provided
        if logos:
            logo_files = [{"filename": file.filename, "content": await file.read()} for file in logos]
            uploaded_logo_urls = gcs_client.upload_to_gcs(
                files=logo_files,
                folder=f"organizations/{get_organization_acronym(org.name)}/logos"
            )
            # organization_data["logos"] = {
            #     file.filename: url for file, url in zip(logos, uploaded_logo_urls)
            # }
            organization_data["logos"] =uploaded_logo_urls
        else:
            # Maintain existing data if logos are not provided
            organization_data.pop("logos", None)
        

        # logo_urls={}
        # # Process uploaded files for logos
        # if logos:
        #     logo_files = [{"filename": file.filename, "content": await file.read()} for file in logos]
          
        #     logo_urls = gcs_client.upload_to_gcs(files=logo_files, folder=f"organizations/{get_organization_acronym(name)}/logos") or {}
          

        # Process uploaded user images if provided
        if user_images:
            user_files = [{"filename": file.filename, "content": await file.read()} for file in user_images]
            uploaded_image_urls = gcs_client.upload_to_gcs(
                files=user_files,
                folder=f"organizations/{get_organization_acronym(org.name)}/user_profiles"
            )
            uploaded_image_urls_list = list(uploaded_image_urls.values())
            for i, user in enumerate(organization_data.get("users", [])):
                if i < len(uploaded_image_urls_list):
                    user["image_path"] = uploaded_image_urls_list[i]
        else:
            # Ensure user image paths are not overwritten if no new images are provided
            for user in organization_data.get("users", []):
                user.pop("image_path", None)

        # Perform the update using the `update_with_nested` function
        updated_organization = organization_crud.update_with_nested(
            db=db,
            db_obj=org,
            obj_in=organization_data  # Pass the dynamic dictionary
        )

        return updated_organization

    except HTTPException as e:
        logger.error(f"HTTP exception during update: {e.detail}")
        raise e
    except Exception as e:
        logger.exception("Unexpected error during update_organization.")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")



@app.delete("/v2/delete/{id}", response_model=None)
def delete_record(
    id: UUID,
    confirm: bool = Query(False, description="Confirm cascading deletion of related records."),
    db: Session = Depends(get_db),
):
    """
    Deletes a record and its related references.

    - If the record has related references, pass `confirm=True` to cascade delete.
    - Returns 404 if the record is not found.
    - Returns 400 if there are related references and `confirm` is not set to `True`.
    """
    try:
        organization_crud.delete_with_references(db=db, id=id, confirm=confirm)
        return {"detail": f"Record with ID {id} successfully deleted."}
    except HTTPException as e:
        logger.error(f"HTTP exception during deletion: {e.detail}")
        raise e
    except Exception as e:
        logger.exception("Unexpected error during record deletion.")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")



#Branches
@app.post("/{org_id}/branches", response_model=BranchOut)
async def create_organization_branch(org_id: uuid.UUID, branch_in: BranchCreate, db: Session = Depends(get_db)):
    branch = create_branch(db, branch_in, organization_id=org_id)
    asyncio.create_task(push_summary_update(db, str(org_id)))
    return branch

@app.get("/{org_id}/branches", response_model=list[BranchOut])
def list_organization_branches(org_id: uuid.UUID, db: Session = Depends(get_db), skip: int = 0, limit: int = 10):
    return get_branches(db, organization_id=org_id, skip=skip, limit=limit)

@app.get("/{org_id}/branches/{branch_id}", response_model=BranchOut)
def get_branch_endpoint(org_id: uuid.UUID, branch_id: uuid.UUID, db: Session = Depends(get_db)):
    branch = get_branch(db, branch_id)
    if not branch or branch.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch

@app.patch("/{org_id}/branches/{branch_id}", response_model=BranchOut)
async def update_branch_endpoint(org_id: uuid.UUID, branch_id: uuid.UUID, branch_in: BranchUpdate, db: Session = Depends(get_db)):
    branch = get_branch(db, branch_id)
    if not branch or branch.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    data = update_branch(db, branch, branch_in)
    asyncio.create_task(push_summary_update(db, str(org_id)))
    return data

@app.delete("/{org_id}/branches/{branch_id}")
async def delete_branch_endpoint(org_id: uuid.UUID, branch_id: uuid.UUID, db: Session = Depends(get_db)):
    branch = get_branch(db, branch_id)
    if not branch or branch.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    delete_branch(db, branch)
    asyncio.create_task(push_summary_update(db, str(org_id)))
    return {"detail": "Branch deleted successfully"}

























# @app.put("/upd/{organization_id}", response_model=OrganizationSchema)
# def update_organization(
#     organization_id: UUID,
#     organization_update: OrganizationCreateSchema,
#     logo: Optional[UploadFile] = File(None),
#     db: Session = Depends(get_db),
# ):
#     """
#     Update an organization by ID and handle nested updates.
#     """
#     org = organization_crud.get(db, id=organization_id)
#     if not org:
#         raise HTTPException(status_code=404, detail="Organization not found")

#     update_data = organization_update.dict(exclude_unset=True)
#     if logo:
#         update_data["logos"] = logo

    
#     return organization_crud.update_with_nested(db, db_obj=org, obj_in=update_data)




# @app.put("/v2/upd/{organization_id}", response_model=OrganizationSchema)
# async def update_organization(
#     organization_id: UUID,
#     organization_update: Optional[str] = Form(...),  # Accept JSON string for updates
#     logos: Optional[List[UploadFile]] = File(None),  # Upload files for logos
#     user_images: Optional[List[UploadFile]] = File(None),  # Upload files for user profile images
#     db: Session = Depends(get_db),
# ):
#     try:
#         org = db.query(Organization).filter(Organization.id == organization_id).first()
#         if not org:
#             raise HTTPException(status_code=404, detail="Organization not found")

#         if organization_update:
#             try:
#                 organization_data = json.loads(organization_update)
#             except json.JSONDecodeError as e:
#                 raise HTTPException(status_code=400, detail="Invalid JSON format for organization_update") from e
#         else:
#             organization_data = {}

#         config = DevelopmentConfig()
#         bucket_name = config.BUCKET_NAME
#         gcs_client = GoogleCloudStorage(bucket_name)

#         if logos:
#             logo_files = [{"filename": file.filename, "content": await file.read()} for file in logos]
#             uploaded_logo_urls = gcs_client.upload_to_gcs(
#                 files=logo_files,
#                 folder=f"organizations/{org.name}/logos"
#             )
#             organization_data["logos"] = serialize_for_json({
#                 file.filename: url for file, url in zip(logos, uploaded_logo_urls)
#             })
        

#         # Process uploaded user images
#         if user_images:
#             user_files = [{"filename": file.filename, "content": await file.read()} for file in user_images]
#             uploaded_image_urls = gcs_client.upload_to_gcs(
#                 files=user_files,
#                 folder=f"organizations/{org.name}/user_profiles"
#             )
#             uploaded_image_urls_list = list(uploaded_image_urls.values())
#             for i, user in enumerate(organization_data.get("users", [])):
#                 if i < len(uploaded_image_urls_list):
#                     user["image_path"] = uploaded_image_urls_list[i]

#           # Perform the update using the `update_with_nested` function
#         updated_organization = organization_crud.update_with_nested(
#             db=db,
#             db_obj=org,
#             obj_in=organization_data
#         )
#         return updated_organization

#     except HTTPException as e:
#         logger.error(f"HTTP exception during update: {e.detail}")
#         raise e
#     except Exception as e:
#         logger.exception("Unexpected error during update_organization.")
#         raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")










