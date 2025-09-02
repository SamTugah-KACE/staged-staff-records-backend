import json
import os
from pydantic import  Field, EmailStr, field_validator
from typing import Any, Dict, List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
import secrets
from functools import lru_cache


class BaseConfig(BaseSettings):
    """
    Base configuration for the application.
    """
    APP_NAME: str = Field("User Management System", description="The name of the application.")
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT", description="Application environment (development, production, testing).")
    DEBUG: bool = Field(False, description="Debug mode for the application.")
    # secrets.token_urlsafe(32)
    # SECRET_KEY: str = Field(..., env="SECRET_KEY", description="Secret key for application security.")
    SECRET_KEY: str = Field(secrets.token_urlsafe(32), env="SECRET_KEY", description="Secret key for application security.")
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    COOKIE_REFRESH_EXPIRE = 290500
    # Cookie settings
    COOKIE_NAME:str = "refresh_token"
    COOKIE_SECURE:bool = True            # send only over HTTPS
    COOKIE_HTTPONLY:bool = True          # not accessible via JS
    COOKIE_SAMESITE:str = "lax"       # CSRF protection
    COOKIE_PATH:str = "/"

    ACCESS_TOKEN_EXPIRE_MINUTES:int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 480))
    REFRESH_TOKEN_EXPIRE_DAYS:int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

    # … existing fields …
    API_BASE_URL: str = Field(
        "http://localhost:8000",
        env="API_BASE_URL",
        description="Public base URL of this API, e.g. https://api.myapp.com",
    )

    TENANT_URL: str = Field(
        "",
        env="TENANT_URL",
        description="Public base URL of the tenant service, e.g. https://tenant.myapp.com",
    )
    
    # Database Configurations
    DATABASE_URL: str = Field("postgresql://postgres:password@localhost/records_db", env="DATABASE_URL", description="Database connection string.")

    #Token Configuration
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 2700
    REFRESH_TOKEN_DURATION_IN_MINUTES: int =  2592000
    REMEMBER_ME_REFRESH_TOKEN_IN_MINUTES: int = 5184000
    REFRESH_TOKEN_REMEMBER_ME_DAYS: int = 60
    COOKIE_ACCESS_EXPIRE: int = 1800
    COOKIE_REFRESH_EXPIRE: int = 2592000 # 1 Month


    #External api
    FACIAL_AUTH_API_URL:str = 'https://facial-authentication-system.onrender.com/'
    FACIAL_AUTH_API_TIMEOUT:int = 120  # 120 seconds


    SENDGRID_API_KEY: str = Field(..., env="SENDGRID_API_KEY")
    
    MAIL_USERNAME: str =Field(..., env="MAIL_USERNAME")
    MAIL_PASSWORD: str =Field(..., env="MAIL_PASSWORD") #palvpbokbnisspps
    MAIL_FROM: str =Field(..., env="MAIL_FROM", description="Sender email address for SMTP.")
    MAIL_PORT: int =Field(..., env="MAIL_PORT")
    MAIL_SERVER: str =Field(..., env="MAIL_SERVER", description="SMTP host.")
    MAIL_STARTTLS: bool = Field(..., env="MAIL_STARTTLS")
    MAIL_SSL_TLS: bool =Field(..., env="MAIL_SSL_TLS")
    USE_CREDENTIALS: bool = Field(..., env="USE_CREDENTIALS")
    VALIDATE_CERTS: bool = Field(..., env="VALIDATE_CERTS")

    PROVIDER: str = Field(..., env="PROVIDER", description="Client Email Service Provider. 'smtp' | 'sendgrid' ")

    # Logging
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL", description="Logging level (DEBUG, INFO, WARNING, ERROR).")

    SUPERADMIN_UI_URL: str = Field(..., env="SUPERADMIN_UI_URL", description="Superadmin UI URL.")

    # Production-ready seed data for roles and their permissions.
    DEFAULT_ROLE_PERMISSIONS: List[Dict[str, Any]] = Field(
    default = [
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
    },
    {
        "name": "Manager",
        "permissions": [
            "employee:read",
            "employee:update",
            "role:manage",
            "audit:read",
            "user:dashboard",
            "user:dashboard:settings",
        ],
    },
    {
        "name": "Super Admin",
        "permissions": [
            "permissions:manage",
            "organization:create",
            "organization:update",
            "organization:read",
            "hr:dashboard",
            "admin:dashboard",
            "hr:dashboard:settings",
            "admin:dashboard:settings",
            "admin:dashboard:permissions",
            "admin:dashboard:notifications",
            "admin:dashboard:alerts",
            "admin:dashboard:logs",
            "admin:dashboard:history",
            "admin:dashboard:comments",
            "admin:dashboard:feedback",
            "admin:dashboard:reviews",
            "admin:dashboard:ratings",
            "admin:dashboard:tags",
            "super_admin:dashboard",
            "super_admin:dashboard:settings",
            "super_admin:dashboard:permissions",
            "super_admin:dashboard:notifications",
            "super_admin:dashboard:alerts",
            
        ],
    },
    {
        "name": "CEO",
        "permissions": [
            "employee:create",
            "employee:read",
            "employee:update",
            "employee:delete",
            "employee:archive",
            "employee:transfer",
            "attendance:record",
            "role:manage",
            "user:assignRole",
            "audit:read",
            "organization:manage",
            "hr:dashboard",
            "hr:dashboard:read",
        ],
    },
    {
        "name": "HR Manager",
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
    },
    {
        "name": "Department Head",
        "permissions": [
            "employee:read",
            "employee:update",
            "department:head:dashboard",
            "department:manage",
        ],
    },
    {
        "name": "Branch Manager",
        "permissions": [
            "employee:read",
            "employee:update",
            "branch:manager:dashboard",
            "branch:manage",
        ],
    },
    {
        "name": "Employee",
        "permissions": [
            "employee:read",
            "staff:dashboard",
        ],
    },
    
     {
        "name": "Staff",
        "permissions": [
            "staff:read",
            "staff:dashboard",
        ],
    },

     {
        "name": "HoD",
        "permissions": [
            "hod:dashboard",
            "staff:list:read",
            "staff:list:update",
            "staff:leave:manage",
        ],
    },
    
    # Add additional roles as needed...
    ],
        env="DEFAULT_ROLE_PERMISSIONS",
        description="Default roles and their permissions.",
    )
    # Default permissions for user roles.

    #Permissions
    DEFAULT_PERMISSIONS: List[str] = Field(
        default = [
    # --- Employee Records Management ---
    "employee:create",          # Create new employee records
    "employee:read",            # View employee details
    "employee:update",          # Update employee records
    "employee:delete",          # Delete employee records
    "employee:archive",         # Archive employee records
    "employee:transfer",        # Transfer employee between departments

    # --- Organizational & Role Management ---
    "organization:read",        # View organization details and settings
    "organization:update",      # Modify organization configurations
    "role:manage",              # Create, update, delete roles and assign permissions
    "user:assignRole",          # Assign roles to users
    "audit:read",               # View audit logs

    # --- Attendance and Time Tracking ---
    "attendance:record",        # Record or adjust attendance entries
    "attendance:read",          # View attendance records
    "attendance:update",        # Update attendance information
    "leave:apply",              # Apply for leave
    "leave:approve",            # Approve leave applications
    "leave:manage",             # Manage leave requests (cancel/update)

    # --- Payroll and Benefits Administration ---
    "payroll:process",          # Initiate and oversee payroll processing
    "payroll:read",             # View payroll details and payslips
    "payroll:update",           # Adjust payroll data prior to processing
    "benefits:manage",          # Administer employee benefit programs
    "payroll:report",           # Generate payroll reports

    # --- Recruitment & Onboarding ---
    "recruitment:create",       # Post new job listings and openings
    "recruitment:read",         # View recruitment data and applicant details
    "recruitment:update",       # Update job postings or applicant status
    "recruitment:delete",       # Remove outdated recruitment data
    "onboarding:manage",        # Manage onboarding for new hires

    # --- Performance Management ---
    "performance:review:create",    # Initiate performance review cycles
    "performance:review:read",      # Access performance review records
    "performance:review:update",    # Modify performance reviews as needed
    "performance:goal:manage",      # Set and track employee performance goals

    # --- Security and Compliance ---
    "security:read",            # View security logs and alerts
    "security:update",          # Update security configurations (e.g., policies, MFA)
    "compliance:read",          # Access compliance reports and audit data
    "compliance:update",        # Update compliance-related settings

    # --- Reporting and Analytics ---
    "report:generate",          # Create custom HR reports
    "report:read",              # View pre-generated or dynamic report data

    # --- Dashboard Routing for Dynamic UI ---
    "hr:dashboard",             # Access the HR Manager Dashboard view
    "department:head:dashboard",# Access the Department Head Dashboard view
    "staff:dashboard",          # Access the generic Staff Dashboard view
    "admin:dashboard",          # Access the Admin Dashboard view
    "manager:dashboard",        # Access the Manager Dashboard view
    "branch:manager:dashboard", # Access the Branch Manager Dashboard view
    "finance:dashboard",        # Access the Finance Dashboard view
    
    "hr:dashboard:read",        # View HR Dashboard data
    "hr:dashboard:update",      # Update HR Dashboard settings
    "hr:dashboard:create",      # Create new HR Dashboard entries
    "hr:dashboard:delete",      # Delete HR Dashboard entries
    
    "hr:dashboard:archive",     # Archive HR Dashboard entries
    "hr:dashboard:transfer",    # Transfer HR Dashboard entries
    
    "hr:dashboard:report",      # Generate HR Dashboard reports
    "hr:dashboard:analytics",   # Access HR Dashboard analytics
    "hr:dashboard:permissions", # Manage HR Dashboard permissions
    "hr:dashboard:settings",    # Update HR Dashboard settings
    "hr:dashboard:notifications",# Manage HR Dashboard notifications
    "hr:dashboard:alerts",      # View HR Dashboard alerts
    "hr:dashboard:logs",        # Access HR Dashboard logs
    "hr:dashboard:history",     # View HR Dashboard history
    "hr:dashboard:comments",    # Manage HR Dashboard comments
    "hr:dashboard:feedback",    # Provide feedback on HR Dashboard entries
    "hr:dashboard:reviews",     # Manage HR Dashboard reviews
    "hr:dashboard:ratings",     # Rate HR Dashboard entries
    "hr:dashboard:tags",        # Tag HR Dashboard entries
    "hr:dashboard:categories",  # Categorize HR Dashboard entries
    "hr:dashboard:groups",      # Group HR Dashboard entries
    "hr:dashboard:filters",     # Filter HR Dashboard entries
    "hr:dashboard:search",      # Search HR Dashboard entries
    "hr:dashboard:sort",        # Sort HR Dashboard entries
    "hr:dashboard:export",      # Export HR Dashboard entries
    "hr:dashboard:import",      # Import HR Dashboard entries
    "hr:dashboard:sync",        # Sync HR Dashboard entries
    "hr:dashboard:backup",      # Backup HR Dashboard entries
    "hr:dashboard:restore",     # Restore HR Dashboard entries
    "hr:dashboard:clone",       # Clone HR Dashboard entries
    "hr:dashboard:duplicate",   # Duplicate HR Dashboard entries
    "hr:dashboard:merge",       # Merge HR Dashboard entries
    "hr:dashboard:split",       # Split HR Dashboard entries
    "hr:dashboard:combine",     # Combine HR Dashboard entries
    "hr:dashboard:link",        # Link HR Dashboard entries
    "hr:dashboard:unlink",      # Unlink HR Dashboard entries
    "hr:dashboard:connect",     # Connect HR Dashboard entries
    "hr:dashboard:disconnect",  # Disconnect HR Dashboard entries
    "hr:dashboard:integrate",   # Integrate HR Dashboard entries
    "hr:dashboard:api",         # Access HR Dashboard API
    "hr:dashboard:webhook",     # Manage HR Dashboard webhooks
    "hr:dashboard:events",      # Manage HR Dashboard events
    "hr:dashboard:triggers",    # Manage HR Dashboard triggers
    "hr:dashboard:actions",     # Manage HR Dashboard actions
    "hr:dashboard:workflows",   # Manage HR Dashboard workflows
    "hr:dashboard:processes",   # Manage HR Dashboard processes
    "hr:dashboard:tasks",       # Manage HR Dashboard tasks
    "hr:dashboard:jobs",        # Manage HR Dashboard jobs
    "hr:dashboard:queues",      # Manage HR Dashboard queues
    "hr:dashboard:threads",     # Manage HR Dashboard threads
    "hr:dashboard:workers",     # Manage HR Dashboard workers
    "hr:dashboard:services",    # Manage HR Dashboard services
    "hr:dashboard:applications",# Manage HR Dashboard applications
    "hr:dashboard:platforms",   # Manage HR Dashboard platforms




    ],
        env="DEFAULT_PERMISSIONS",
        description="Default permissions for user roles.",
    )

    # Bulk Operation Configurations
    BULK_OPERATION_CONCURRENCY_LIMIT: int = Field(10, description="Maximum number of concurrent tasks for bulk operations.")

    # Email Retry Logic
    EMAIL_RETRY_ATTEMPTS: int = Field(3, description="Number of retry attempts for sending emails.")
    EMAIL_RETRY_DELAY: float = Field(1.0, description="Delay between email retries (in seconds).")

    GCS_CREDENTIALS: dict = Field(..., env="GCS_CREDENTIALS")  # We want this as a dict
    @field_validator("GCS_CREDENTIALS", mode="before")
    def parse_gcs_credentials(cls, value):
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("GCS_CREDENTIALS is empty. Please provide valid JSON credentials.")
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON for GCS_CREDENTIALS: {e}")
        return value
    
    EXCEL_FILE_NAME:str = Field("sample_staff_records.xlsx", env="EXCEL_FILE_NAME", description="Name of the sample Excel file.")
    EXCEL_FILE_NAME_SINGLE:str = Field("sample_staff_records_.xlsx", env="EXCEL_FILE_NAME_SINGLE", description="Name of the sample excel file for single managed organization")
    # EXCEL_FILE_URL:str = Field("https://gi-kace-solutions.onrender.com/api/download/download-excel", env="EXCEL_FILE_URL", description="URL to download the sample Excel file.")
    EXCEL_FILE_URL:str = Field(f"{TENANT_URL}/api/download/download-excel", env="EXCEL_FILE_URL", description="URL to download the sample Excel file.")
    EXCEL_FILE_PATH:str = "App/Apis/"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra fields in the config


class DevelopmentConfig(BaseConfig):
    """
    Configuration for the development environment.
    """
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    BUCKET_NAME: str = Field("", env="BUCKET_NAME", description="Google Cloud Storage bucket name.")
    # GOOGLE_APPLICATION_CREDENTIALS:str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    # os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'service_account.json'

class ProductionConfig(BaseConfig):
    """
    Configuration for the production environment.
    """
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    GCS_BUCKET: str = Field("developers-bucket", env="BUCKET_NAME", description="Google Cloud Storage bucket name.")
    BUCKET_NAME: str = Field("developers-bucket", env="BUCKET_NAME", description="Google Cloud Storage bucket name.")
    # GOOGLE_APPLICATION_CREDENTIALS:str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    # os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'service_account.json'
    #AWS S3
    AWS_ACCESS_KEY: str = Field(..., env="AWS_ACCESS_KEY", description="AWS Access Key ID.")
    AWS_SECRET_KEY: str = Field(..., env="AWS_SECRET_KEY", description="AWS Secret Access Key.")
    AWS_REGION: str = Field(..., env="AWS_REGION", description="AWS Region.")
    AWS_S3_BUCKET: str = Field(..., env="AWS_BUCKET_NAME", description="AWS S3 Bucket name.")

    #Local File Storage
    STORAGE_ROOT:str      = Field("/mnt/data/file_storage", env="STORAGE_ROOT") #os.getenv("STORAGE_ROOT", "/mnt/data/file_storage")

    # Arkesel SMS
    ARKESEL_API_KEY: str = Field(..., env="ARKESEL_API_KEY", description="Arkesel API key for SMS service.")
    ARKESEL_SENDER_ID: str = Field(..., env="ARKESEL_SENDER_ID", description="Sender ID for Arkesel SMS service.")
    ARKESEL_API_URL: str = Field(..., env="ARKESEL_API_URL", description="Arkesel API URL for SMS service.")
    ARKESEL_TIMEOUT: int = Field(10, env="ARKESEL_TIMEOUT", description="Timeout for Arkesel API requests in seconds.")
    ARKESEL_API_RETRY_ATTEMPTS: int = Field(3, env="ARKESEL_API_RETRY_ATTEMPTS", description="Number of retry attempts for Arkesel API requests.")
    ARKESEL_USE_CASE: str = Field(..., env="ARKESEL_USE_CASE", description="Use case for Arkesel SMS service.")



class TestingConfig(BaseConfig):
    """
    Configuration for the testing environment.
    """
    DEBUG: bool = True
    DATABASE_URL: str = "sqlite:///./test.db"
    LOG_LEVEL: str = "DEBUG"

@lru_cache()
def get_config():
    """
    Load configuration based on the environment.
    """
    environment = os.getenv("ENVIRONMENT", "DEVELOPMENT").lower()
    if environment == "production":
        return ProductionConfig()
    elif environment == "testing":
        return TestingConfig()
    else:
        return DevelopmentConfig()


# Load the appropriate configuration
config = get_config()
