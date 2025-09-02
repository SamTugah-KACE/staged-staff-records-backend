# dashboard_routes.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from Crud.crud_dashboard import (
    create_dashboard,
    update_dashboard,
    get_dashboards_by_org,
    get_dashboard_by_id,
    compileDynamicSubmitCode,
    get_dashboard_by_user_org
)
from Schemas.schemas import DashboardCreateSchema, DashboardSchema
from Crud.auth import get_db, require_permissions  # RBAC dependency from earlier
from Utils.config import get_config

router = APIRouter()


@router.post("/upsert", response_model=DashboardSchema, status_code=status.HTTP_201_CREATED)
async def upsert_dashboard(
    dashboard_in: DashboardCreateSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions(["employee:create"]))
):
    """
    Create or update a dashboard for the given organization. If a dashboard for
    the same user within the given organization already exists, it will be updated
    either partially or completely based on the provided payload.

    The function makes sure to compile the dashboard’s submit code from its fields.
    """
    try:
        # Use the user_id provided in payload or fall back to the authenticated user.
        user_id = dashboard_in.user_id or current_user.get("id")
        organization_id = dashboard_in.organization_id

        # Check if a dashboard already exists for the user in this organization.
        existing_dashboard = get_dashboard_by_user_org(db, user_id, organization_id)
        
        # Prepare dashboard data if provided
        if dashboard_in.dashboard_data:
            # Get the form design and fields.
            form_design = dashboard_in.dashboard_data
            form_fields = form_design.get("fields", [])
            config = get_config()
            api_url = f"{config.API_BASE_URL}/api/organizations/create-url"
            # The API URL may come from config in production; hard-coded here for demonstration.
            #api_url = "https://staff-records-backend.onrender.com/api/organizations/create-url"
            compiled_code = compileDynamicSubmitCode(form_fields, api_url)
            form_design["submitCode"] = compiled_code
            # Update the incoming payload with the compiled submit code.
            dashboard_in.dashboard_data = form_design

        # If found, update; otherwise, create a new dashboard.
        if existing_dashboard:
            # Use update schema logic: only update provided fields.
            update_data = dashboard_in.dict(exclude_unset=True)
            # Remove organizational keys if present – these should not change.
            update_data.pop("organization_id", None)
            update_data.pop("user_id", None)
            updated_dashboard = update_dashboard(db, existing_dashboard.id, update_data)
            return updated_dashboard
        else:
            # Ensure the new record has the proper user_id set.
            # dashboard_dict = dashboard_in.dict()
            # dashboard_dict["user_id"] = user_id
            new_dashboard = create_dashboard(db, dashboard_in)
            return new_dashboard

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upsert dashboard: {str(e)}"
        )



# @router.post("/", response_model=DashboardSchema, status_code=status.HTTP_201_CREATED)
# async def create_dashboard_endpoint(
#     dashboard_in: DashboardCreateSchema,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(require_permissions(["employee:create"]))
#     # current_user: dict = Depends(require_permissions(["employee:create:dashboard"]))
# ):
#     """
#     Create a new dashboard entry.
    
#     Only users with permission `role:manage_dashboard` (or an equivalent) can create a dashboard.
#     """
#     try:
#         form_design = dashboard_in.dashboard_data  # Expecting a dict with "fields"
#         form_fields = form_design.get("fields", [])
#         # Obtain the API URL from configuration or prefetch logic:
#         api_url = f"https://staff-records-backend.onrender.com/api/organizations/create-url"
#         compiledCode = compileDynamicSubmitCode(form_fields, api_url)
#         form_design["submitCode"] = compiledCode
#         dashboard_in.dashboard_data = form_design
#         new_dashboard = create_dashboard(db, dashboard_in)
#         return new_dashboard
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to create dashboard: {str(e)}"
#         )

@router.put("/{dashboard_id}", response_model=DashboardSchema, status_code=status.HTTP_200_OK)
async def update_dashboard_endpoint(
    dashboard_id: UUID = Path(..., description="ID of the dashboard to update"),
    updated_data: dict = None,  # Can also create a dedicated update schema for validations
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions(["employee:update:dashboard"]))
):
    """
    Update an existing dashboard.
    
    Only users with appropriate permissions can update dashboard settings.
    """
    try:
        
        updated_dashboard = update_dashboard(db, dashboard_id, updated_data)
        return updated_dashboard
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update dashboard: {str(e)}"
        )

@router.get("/", response_model=List[DashboardSchema], status_code=status.HTTP_200_OK)
async def list_dashboards(
    organization_id: UUID = Query(..., description="Organization id to fetch dashboards for"),
    db: Session = Depends(get_db),
    # current_user: dict = Depends(require_permissions(["dashboard:;view"]))
    current_user: dict = Depends(require_permissions(["hr:dashboard:read"]))
):
    """
    Retrieve all dashboards for a specific organization.
    """
    try:
        
        dashboards = get_dashboards_by_org(db, organization_id)
        return dashboards
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve dashboards: {str(e)}"
        )

@router.get("/{dashboard_id}", response_model=DashboardSchema, status_code=status.HTTP_200_OK)
async def get_dashboard_endpoint(
    dashboard_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions(["employee:read:dashboard"]))
):
    """
    Retrieve a dashboard by ID.
    """
    try:
        
        dashboard = get_dashboard_by_id(db, dashboard_id)
        return dashboard
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dashboard: {str(e)}"
        )
