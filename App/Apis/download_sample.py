import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from Models.Tenants.organization import Organization
from database.db_session import get_db

logger = logging.getLogger(__name__)

# Configuration - use default values that match the actual files
EXCEL_FILE_NAME = "sample_staff_records.xlsx"
EXCEL_FILE_NAME_SINGLE = "sample_staff_records_.xlsx"

# Get the directory where this script is located (absolute path)
# This should work regardless of the server's working directory
BASE_DIR = Path(__file__).resolve().parent
FILE_PATH = BASE_DIR / EXCEL_FILE_NAME

# Debug logging
logger.info("Download sample configuration:")
logger.info("  EXCEL_FILE_NAME: %s", EXCEL_FILE_NAME)
logger.info("  EXCEL_FILE_NAME_SINGLE: %s", EXCEL_FILE_NAME_SINGLE)
logger.info("  BASE_DIR resolved to: %s", BASE_DIR)
logger.info("  Files in BASE_DIR: %s", list(BASE_DIR.glob("*.xlsx")))
logger.info("  FILE_PATH: %s", FILE_PATH)
logger.info("  FILE_PATH exists: %s", FILE_PATH.exists())



router = APIRouter()


@router.get(
    "/sample-file/{organization_id}",
    # response_class=FileResponse,
    tags=["Download Sample File"],
    summary="Download the Excel file",
    response_description="The Excel file"
)
async def download_excel(
    organization_id: str,  # Assuming organization_id is a string, adjust as necessary
    db: Session = Depends(get_db),  # Uncomment if you need database access
    # current_user: dict = Depends(require_permissions(["hr:dashboard:read"]))  # Uncomment if you need user permissions
):
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if not org:
        logger.error("Organization not found: %s", organization_id)
        raise HTTPException(status_code=404, detail="Organization not found")
    
    org_nature = org.nature.strip().lower() if org.nature else "unknown"
    
    # Determine which file to serve based on organization nature
    if "single" in org_nature:
        logger.info("Serving single organization file: %s", EXCEL_FILE_NAME_SINGLE)
        file_path = BASE_DIR / EXCEL_FILE_NAME_SINGLE
        filename = EXCEL_FILE_NAME_SINGLE
    else:
        logger.info("Serving multi-organization file: %s", EXCEL_FILE_NAME)
        file_path = BASE_DIR / EXCEL_FILE_NAME
        filename = EXCEL_FILE_NAME
    
    logger.info("Download request received for file: %s", file_path)
    logger.info("BASE_DIR: %s", BASE_DIR)
    logger.info("File path exists: %s", file_path.exists())

    # Check if the file exists
    if not file_path.exists():
        logger.error("File not found: %s", file_path)
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        logger.info("Serving file: %s", file_path)
        return FileResponse(
            path=str(file_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename
        )
    except Exception as e:
        logger.exception("Error while sending the file: %s", e)
        raise HTTPException(status_code=500, detail="Internal Server Error") from e