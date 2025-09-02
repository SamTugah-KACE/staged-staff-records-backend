# models/dynamic_models.py

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from database.db_session import BaseModel
from sqlalchemy.orm import relationship

class EmployeeDynamicData(BaseModel):
    """
    Stores additional employee data that may vary by organization.
    Each record links to an Employee and groups extra key/value pairs.
    """
    __tablename__ = "employee_dynamic_data"

    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    data_category = Column(String, nullable=False)  # e.g., "benefits", "custom_fields", or sheet name
    data = Column(JSONB, nullable=False)  # Store extra columns as JSON

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", backref="dynamic_data")


class BulkUploadError(BaseModel):
    """
    Captures rows that failed to insert during the bulk employee upload.
    These errors can be retried or presented to the client for manual correction.
    """
    __tablename__ = "bulk_upload_errors"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String, nullable=False)
    error_details = Column(JSONB, nullable=False)  # e.g., list of {row_number, error_message, data}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
