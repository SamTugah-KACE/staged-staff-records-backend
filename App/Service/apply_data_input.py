# src/services/apply_data_input.py
import logging
from sqlalchemy.orm import Session
from Models.models import EmployeeDataInput
from Service.data_input_handlers import get_handler

logger = logging.getLogger(__name__)

# def apply_data_input(db: Session, record: EmployeeDataInput):
#     """
#     Called when an EmployeeDataInput.status transitions to Approved.
#     Dispatches to the handler registered for record.data_type.
#     """
#     try:
#         print("\n\nrecord", record)
#         print("\n\nrecord.data_type", record.data_type)
#         print("\n\nrecord.data", record.data)
#         print("\n\nrecord.employee_id", record.employee_id)
#         print("\n\nrecord.organization_id", record.organization_id)
#         print("\n\nrecord.request_type", record.request_type)
#         if record and record.organization_id:
#             # models like academic qualifications, professional qualifications, etc. have event trigger on both insert and update for filestorage where media files storage paths for all other models are backed up to the filestorage table.
#             # This table requires the organization_id to be set for a complete backup.
#             if record.data_type in ["academic_qualifications", "professional_qualifications"]:
#                 # Check if the organization_id is set
#                 if not record.organization_id:
#                     raise ValueError("organization_id must be set for this data_type")
                
#                 #set the organization_id to the record as an attribute so that the trigger can pick it up
#                 setattr(record, "organization_id", record.organization_id)
#                 # Check if the file storage service is set

#         # with db.begin():  # atomic transaction
#         handler = get_handler(record.data_type)
#         logger.info("Applied data_input %s to %s", record.id, record.data_type)
#     except Exception:
#         logger.exception("Error applying data_input %s", record.id)
#         raise

#     # Delegate to the handler (which also handles save vs update)
#     handler(db, record)
#     logger.info("Applied data_input %s to model %s", record.id, record.data_type)

def apply_data_input(db: Session, record: 'EmployeeDataInput'):
    handler = get_handler(record.data_type)
    try:
        # with db.begin():  # atomic transaction
        handler(db, record)
        logger.info("Applied data_input %s to %s", record.id, record.data_type)
    except Exception:
        logger.exception("Error applying data_input %s", record.id)
        raise