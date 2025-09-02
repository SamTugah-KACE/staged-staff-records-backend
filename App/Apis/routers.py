from fastapi import FastAPI, APIRouter
# from .apis import (
#     organization,
#     role,
#     user,
#     employee,
#     academic_qualification,
#     employment_history,
#     emergency_contact,
#     next_of_kin,
#     file_storage,
# ) 
# from .organization import router as organization
from .main import app as organization
from .uploadfile import app as uploadfile
from .default import app as bank
from .user_api import router as user
from .apis import router as mix
from .auth import router as auth
from .promotions import router as promo
from .tenant_apis import router as tenant
from .dashboard_routes import router as dashboard
from .download_sample import router as download_sample
from .super_auth import router as super_auth
from .employee_requests import router as emp_req
from .summary import router as summary
from .ws_employee import router as emp_ws
from .UserBase import router as user_base
from .employee_download import router as employee_download
from .ws_summary import router as summary_ws
# from notification.socket import router as notif

api =APIRouter()

# Include Routers
api.include_router(summary, prefix="/api")
api.include_router(summary_ws)
api.include_router(emp_ws)
api.include_router(super_auth, prefix="/api/super-auth", tags=["Super Auth"])
api.include_router(uploadfile, prefix="/api/uploadfile", tags=["UploadFile"])
api.include_router(download_sample, prefix="/api/download", tags=["Download Sample File"])
api.include_router(bank, prefix="/api/default", tags=["Defaults"])
api.include_router(auth, prefix="/api/auth", tags=["Auth"])
api.include_router(dashboard, prefix="/api/dashboards", tags=["Dashboards"])
api.include_router(user, prefix="/api/users", tags=["User Management"])
api.include_router(employee_download, prefix="/api/download-employee-data", tags=["Employee Download"])
api.include_router(user_base)
api.include_router(mix, prefix="/api")
api.include_router(emp_req, prefix="/api")
api.include_router(organization, prefix="/api/organizations", tags=["Organizations"])
api.include_router(promo, prefix="/api/promotions", tags=["Organizational Promotions"])
api.include_router(tenant, prefix="/api")




# api.include_router(notif, prefix="/api/notification", tags=["Notifications"])


# api.include_router(employee.router, prefix="/api/employees", tags=["Employees"])
# api.include_router(academic_qualification.router, prefix="/api/academic-qualifications", tags=["AcademicQualifications"])
# api.include_router(employment_history.router, prefix="/api/employment-history", tags=["EmploymentHistory"])
# api.include_router(emergency_contact.router, prefix="/api/emergency-contacts", tags=["EmergencyContacts"])
# api.include_router(next_of_kin.router, prefix="/api/next-of-kin", tags=["NextOfKin"])
# api.include_router(file_storage.router, prefix="/api/file-storage", tags=["FileStorage"])