import asyncio
import json
from fastapi import Depends, HTTPException, UploadFile
from sqlalchemy import inspect, String, and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql import exists, or_
from typing import List, Any, Optional, Dict, Union
from pydantic import BaseModel
from uuid import UUID
import pandas as pd
import io
from google.cloud import storage
import logging
from sqlalchemy.sql import and_, or_
from Apis.summary import push_summary_update
from Service.storage_service import BaseStorage
from Utils.storage_utils import get_storage_service
from Utils.util import get_organization_acronym
from Models.Tenants.organization import Organization
from Models.Tenants.role import Role
from Models.models import Employee, User
from Utils.config import DevelopmentConfig, get_config
from Service.gcs_service import GoogleCloudStorage

settings = get_config()

gcs = GoogleCloudStorage(bucket_name=settings.BUCKET_NAME)
# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# import logging
# logging.basicConfig()
# logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)


# Constants for Google Cloud Storage
GCS_BUCKET_NAME = "your_bucket_name"
GCS_BASE_URL = "https://storage.googleapis.com"


class CRUDBase:
    def __init__(self, model, audit_model=None, file_model=None):
        self.model = model
        self.audit_model = audit_model
        self.file_model = file_model

    def log_error(self, error: Exception, operation: str):
        """Log errors for debugging and auditing purposes."""
        logger.error(f"Error during {operation}: {str(error)}")

    def audit_action(self, db: Session, action: str, table_name: str, record_id: Union[UUID, None], user_id: Optional[UUID] = None):
        """Log an action to the audit log."""
        if self.audit_model:
            audit_entry = self.audit_model(
                action=action, table_name=table_name, record_id=record_id, performed_by=user_id
            )
            db.add(audit_entry)
            db.commit()

    def upload_to_gcs(self, file: UploadFile) -> Dict:
        """Upload a file to Google Cloud Storage."""
        try:
            client = storage.Client()
            bucket = client.get_bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(file.filename)
            blob.upload_from_file(file.file, content_type=file.content_type)
            file_url = f"{GCS_BASE_URL}/{GCS_BUCKET_NAME}/{file.filename}"
            return {"file_name": file.filename, "file_path": file_url}
        except Exception as e:
            self.log_error(e, "upload_to_gcs")
            raise HTTPException(status_code=500, detail="Failed to upload file to Google Cloud Storage")



    def upload_multiple_to_gcs(self, files: List[UploadFile]) -> List[Dict]:
        """Upload multiple files to Google Cloud Storage."""
        uploaded_files = []
        for file in files:
            try:
                file_info = self.upload_to_gcs(file)
                uploaded_files.append(file_info)
            except Exception as e:
                self.log_error(e, "upload_multiple_to_gcs")
                raise HTTPException(status_code=500, detail="Failed to upload some files")
        return uploaded_files



    def resolve_reference(self, db: Session, reference: Dict[str, Any]) -> Any:
        """
        Resolve the object reference using primary key, unique, or indexed fields.
        :param reference: Dictionary containing the reference field and value.
        :return: Object matching the reference or raises 404.
        """
        query = db.query(self.model)
        filters = [getattr(self.model, field) == value for field, value in reference.items()]
        obj = query.filter(or_(*filters)).first()
        if not obj:
            raise HTTPException(status_code=404, detail="Item not found with the given reference.")
        return obj
    
    

    def apply_filters(self, query, filters: Dict) -> Any:
        """Apply dynamic filters to a query."""
        filter_conditions = []
        for field, condition in filters.items():
            if isinstance(condition, dict):
                for operator, value in condition.items():
                    if operator == "eq":
                        filter_conditions.append(getattr(self.model, field) == value)
                    elif operator == "lt":
                        filter_conditions.append(getattr(self.model, field) < value)
                    elif operator == "gt":
                        filter_conditions.append(getattr(self.model, field) > value)
                    elif operator == "in":
                        filter_conditions.append(getattr(self.model, field).in_(value))
                    # Add more operators as needed
            else:
                filter_conditions.append(getattr(self.model, field) == condition)
        return query.filter(and_(*filter_conditions))



    # def get(self, db: Session, reference: Dict[str, Any]) -> Any:
    #     """Get a single object by reference."""
    #     try:
    #         obj = self.resolve_reference(db, reference)

    #         # Retrieve associated files if file_model is defined
    #         if self.file_model:
    #             files = db.query(self.file_model).filter(self.file_model.record_id == obj.id).all()
    #             obj.files = files

    #         self.audit_action(db, "read", self.model.__tablename__, obj.id)
    #         return obj
    #     except Exception as e:
    #         self.log_error(e, "get")
    #         raise HTTPException(status_code=500, detail="Internal server error")

    def _to_dict(self, obj: Any) -> dict:
        """
        Helper function to convert a SQLAlchemy model instance into a dict
        by iterating over its column attributes.
        """
        return {col.key: getattr(obj, col.key) for col in inspect(obj).mapper.column_attrs}

    def _process_file_fields(self, data: dict, max_file_size: Optional[int] = None) -> dict:
        """
        Recursively inspects a dictionary representing a record. For any key that contains
        "path" (case-insensitive) and whose value is a URL pointing to GCS, attempt to download
        the file content (base64-encoded) if its size is within max_file_size (if provided).
        
        The downloaded file content is added under a new key (e.g. "profile_image_path_content").
        """
        for key, value in data.items():
            if isinstance(value, dict):
                data[key] = self._process_file_fields(value, max_file_size)
            elif isinstance(value, list):
                processed_list = []
                for item in value:
                    if isinstance(item, dict):
                        processed_list.append(self._process_file_fields(item, max_file_size))
                    else:
                        processed_list.append(item)
                data[key] = processed_list
            else:
                # Check for file URL fields.
                if (
                    isinstance(value, str)
                    and "storage.googleapis.com" in value
                    and "path" in key.lower()
                ):
                    content = gcs.download_from_gcs(value, max_file_size=max_file_size)
                    # Only add the file content if download was successful.
                    if content:
                        data[f"{key}_content"] = content
        return data

    def get(self, db: Session, reference: Dict[str, Any], include_files: bool = False, max_file_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Retrieve a record by its unique identifier (or other unique fields) and ensure that,
        if applicable, an organization_id or employee_id is provided.

        In addition to the main record, this method fetches all related records (based on the model’s
        relationships) and organizes the result into a dictionary with two keys:
        - "main": contains the record for the current model (keyed by the model’s name).
        - "related": a dict keyed by relationship name with the related record(s).

        If include_files is True, then any field whose name contains "path" and stores a GCS URL
        will be processed. If max_file_size is provided, file downloads that exceed that size (in bytes)
        are skipped to protect performance.
        """
        try:
            # --- Enforce Required Identification ---
            if hasattr(self.model, "organization_id") and "organization_id" not in reference:
                raise HTTPException(status_code=400, detail="organization_id is required for this model.")
            if hasattr(self.model, "employee_id") and "employee_id" not in reference:
                raise HTTPException(status_code=400, detail="employee_id is required for this model.")

            # --- Retrieve the Main Record ---
            obj = self.resolve_reference(db, reference)
            if not obj:
                raise HTTPException(status_code=404, detail="Record not found.")
            main_data = self._to_dict(obj)
            if include_files:
                main_data = self._process_file_fields(main_data, max_file_size=max_file_size)

            # --- Retrieve and Organize Related Records ---
            related_data = {}
            mapper = inspect(self.model)
            for rel in mapper.relationships:
                try:
                    rel_value = getattr(obj, rel.key)
                except Exception:
                    continue  # Skip if unable to retrieve relationship
                if not rel_value:
                    continue

                # Process both collection and scalar relationships.
                if isinstance(rel_value, list):
                    processed_list = []
                    for item in rel_value:
                        item_dict = self._to_dict(item)
                        if include_files:
                            item_dict = self._process_file_fields(item_dict, max_file_size=max_file_size)
                        processed_list.append(item_dict)
                    related_data[rel.key] = processed_list
                else:
                    rel_dict = self._to_dict(rel_value)
                    if include_files:
                        rel_dict = self._process_file_fields(rel_dict, max_file_size=max_file_size)
                    related_data[rel.key] = rel_dict

            output = {
                "main": {self.model.__name__: main_data},
                "related": related_data
            }

            self.audit_action(db, "read", self.model.__tablename__, obj.id)
            return output

        except HTTPException as he:
            raise he
        except SQLAlchemyError as e:
            self.log_error(e, "get")
            raise HTTPException(status_code=400, detail="Database error occurred while retrieving the record.")
        except Exception as e:
            self.log_error(e, "get")
            raise HTTPException(status_code=500, detail="Internal server error")
        


    def get_multi(
        self, db: Session, filters: Optional[Dict] = None, skip: int = 0, limit: int = 10, group_by: Optional[str] = None, created_by: Optional[UUID] = None
    ) -> Union[List[Any], Dict[str, Any]]:
        """
        Get multiple objects with optional filters.
        If a group_by field is provided, returns a dict with both the flat list and the grouped dict.
        """
        try:
            query = db.query(self.model)
            print("\n\nquery: ", query)
            if filters:
                query = self.apply_filters(query, filters)
                # for field, value in filters.items():
                #     query = query.filter(getattr(self.model, field) == value)

            # Use `yield_per` for better memory usage in large queries
            objs = query.offset(skip).limit(limit).yield_per(100).all()
            print("query obj: ", objs)
            # Retrieve associated files for each object
            if self.file_model:
                for obj in objs:
                    files = db.query(self.file_model).filter(self.file_model.record_id == obj.id).all()
                    obj.files = files
            
            if group_by:
                grouped_data = {}
                for obj in objs:
                    # Use getattr() to extract the grouping key (e.g. organization_id)
                    key = getattr(obj, group_by, None)
                    if key not in grouped_data:
                        grouped_data[key] = []
                    grouped_data[key].append(obj)
                return {"flat": objs, "grouped": grouped_data}
            else:
                return objs

            # self.audit_action(db, "read_multi", self.model.__tablename__, created_by)
            
        except Exception as e:
            self.log_error(e, "get_multi")
            raise HTTPException(status_code=500, detail="Internal server error")


    async def create_employee(
        self,
        db: Session,
        obj_in: BaseModel,
        unique_fields: Optional[List[str]] = None,
        role_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        file: Optional[UploadFile] = None,
        storage: BaseStorage = Depends(get_storage_service)
    ) -> Any:
        """
        Enhanced create method to handle dependent nested relationships.
        """
        try:

            # Validate that the organization exists and is active.
            org = db.query(Organization).filter(Organization.id == obj_in.organization_id, Organization.is_active.is_(True)).first()
            if not org:
                raise HTTPException(status_code=403, detail="Organization is inactive or does not exist.")
            
            current_user = db.query(User).filter(User.id==user_id, User.organization_id == obj_in.organization_id).first()
            if not current_user:
                raise HTTPException(status_code=403, detail="Current User Cannot Register an Employee belonging to another Organization.")

            # Validate that the role exists for the organization.
            role = (
                db.query(Role)
                .filter(Role.id == role_id, Role.organization_id == obj_in.organization_id)
                .first()
            )
            if not role:
                raise HTTPException(status_code=404, detail="Role does not exist for the given organization.")
            

            # Ensure employee email is unique (within the tenant).
            existing = (
                db.query(Employee)
                .filter(Employee.email == obj_in.email, Employee.organization_id == obj_in.organization_id)
                .first()
            )
            if existing:
                raise HTTPException(status_code=400, detail="An employee with this email already exists.")



            # Validate uniqueness for specified fields
            if unique_fields:
                for field in unique_fields:
                    if db.query(self.model).filter(getattr(self.model, field) == getattr(obj_in, field)).first():
                        raise HTTPException(
                            status_code=400,
                            detail=f"An entry with {field}='{getattr(obj_in, field)}' already exists.",
                        )


            
        

            # Handle file upload if provided
            if file:
                user_files = [{"filename": fil.filename, "content": await fil.read()} for fil in file]
                # uploaded_image_urls = gcs.upload_to_gcs(
                #     files=user_files,
                #     folder=f"organizations/{org.name}/user_profiles"
                # )
                uploaded_image_urls = storage.upload(user_files, f"organizations/{get_organization_acronym(org.name)}/user_profiles") 
            else:
                uploaded_image_urls = ""

            # Convert the uploaded_image_urls to a JSON string if it is a dict
            if isinstance(uploaded_image_urls, dict):
                profile_image_str = json.dumps(uploaded_image_urls)
            else:
                profile_image_str = uploaded_image_urls
                
              

            print("profile image: ", profile_image_str)
            
            new_employee = Employee(
                title = obj_in.title,
                first_name=obj_in.first_name,
                middle_name=obj_in.middle_name,
                last_name=obj_in.last_name,
                gender = obj_in.gender,
                date_of_birth=obj_in.date_of_birth,
                email=obj_in.email,
                is_active = obj_in.is_active,
                contact_info=obj_in.contact_info,
                hire_date=obj_in.hire_date,
                termination_date=obj_in.termination_date,
                custom_data = obj_in.custom_data,
                marital_status = obj_in.marital_status,
                profile_image_path = profile_image_str,
                organization_id=obj_in.organization_id,
                created_by = user_id
            )
            # Attach the role_id as a transient attribute for the event listener.
            new_employee._role_id = role_id
            # Pass the plain password from the API endpoint.
            new_employee._plain_password = getattr(obj_in, "_plain_password", None)
            new_employee._user_image = profile_image_str
            new_employee._created_by = user_id

            db.add(new_employee)
            db.commit()
            db.refresh(new_employee)
            asyncio.create_task(push_summary_update(db, str(obj_in.organization_id)))

            if profile_image_str == "{}" or profile_image_str == "":
                profile_image_str = None

            print("if :: ",profile_image_str)
            if profile_image_str:
                file_entry = self.file_model(
                    file_name=[{"filename": fil.filename} for fil in file],
                    file_path=profile_image_str,
                    uploaded_by_id=user_id,
                    organization_id=obj_in.organization_id,
                    record_id=new_employee.id,
                )
                db.add(file_entry)
                db.commit()
            

            # Audit the creation action
            self.audit_action(db, "create", self.model.__tablename__, new_employee.id, user_id)

            # asyncio.create_task(push_summary_update(db, obj_in.organization_id))
            return new_employee
        

            

            
        except IntegrityError as e:
            db.rollback()
            self.log_error(e, "create")
            raise HTTPException(status_code=400, detail="Database integrity error.")
        except Exception as e:
            db.rollback()
            self.log_error(e, "create")
            raise HTTPException(status_code=500, detail=str(e))
    

    def create(
        self,
        db: Session,
        obj_in: BaseModel,
        unique_fields: Optional[List[str]] = None,
        user_id: Optional[UUID] = None,
        file: Optional[UploadFile] = None,
    ) -> Any:
        """
        Enhanced create method to handle dependent nested relationships.
        """
        try:
            # Validate uniqueness for specified fields
            if unique_fields:
                for field in unique_fields:
                    if db.query(self.model).filter(getattr(self.model, field) == getattr(obj_in, field)).first():
                        raise HTTPException(
                            status_code=400,
                            detail=f"An entry with {field}='{getattr(obj_in, field)}' already exists.",
                        )

            # Prepare data for the main object and nested relationships
            obj_data = obj_in.dict(exclude_unset=True)
            main_obj_data = {k: v for k, v in obj_data.items() if k in self.model.__table__.columns.keys()}
            nested_data = {k: v for k, v in obj_data.items() if k not in main_obj_data}

            # Create dependent nested objects first (e.g., roles before users)
            for field_name, related_items in nested_data.items():
                relationship_property = getattr(self.model, field_name, None)
                if not relationship_property:
                    continue

                related_model = relationship_property.mapper.class_
                if field_name == "roles":  # Create roles first
                    if not isinstance(related_items, list):
                        related_items = [related_items]

                    for item in related_items:
                        if isinstance(item, dict):
                            related_instance = related_model(**item)
                            db.add(related_instance)
                            db.flush()  # Generate IDs for related records

            # Create the main object (e.g., organization)
            db_obj = self.model(**main_obj_data)
            db.add(db_obj)
            db.flush()  # Generate primary key for relationships

            # Handle remaining nested relationships (e.g., users)
            for field_name, related_items in nested_data.items():
                relationship_property = getattr(self.model, field_name, None)
                if not relationship_property or field_name == "roles":
                    continue

                related_model = relationship_property.mapper.class_
                if not isinstance(related_items, list):
                    related_items = [related_items]

                for item in related_items:
                    if isinstance(item, dict):
                        related_instance = related_model(**item)
                        setattr(related_instance, f"{self.model.__tablename__}_id", db_obj.id)  # Set foreign key
                        db.add(related_instance)

            db.commit()
            db.refresh(db_obj)
            asyncio.create_task(push_summary_update(db, str(db_obj.id)))
            # Handle file upload if provided
            if file:
                file_info = self.upload_to_gcs(file)
                file_entry = self.file_model(
                    file_name=file_info["file_name"],
                    file_path=file_info["file_path"],
                    uploaded_by_id=user_id,
                    organization_id=main_obj_data.get("organization_id"),
                    record_id=db_obj.id,
                )
                db.add(file_entry)
                db.commit()

            # Audit the creation action
            self.audit_action(db, "create", self.model.__tablename__, db_obj.id, user_id)
            asyncio.create_task(push_summary_update(db, main_obj_data.get("organization_id")))

            return db_obj
        except IntegrityError as e:
            db.rollback()
            self.log_error(e, "create")
            raise HTTPException(status_code=400, detail=f"Database integrity error.\n{e}")
        except Exception as e:
            db.rollback()
            self.log_error(e, "create")
            raise HTTPException(status_code=500, detail=str(e))










    # def update(
    #     self, 
    #     db: Session, 
    #     reference: Dict[str, Any], 
    #     obj_in: BaseModel, 
    #     unique_fields: Optional[Dict] = None, 
    #     file: Optional[UploadFile] = None
    # ) -> Any:
    #     """
    #     Update an object by reference.
    #     :param reference: Dictionary containing the reference field and value.
    #     """
    #     try:
    #         db_obj = self.resolve_reference(db, reference)

    #         # Prevent updates that conflict with other records
    #         if unique_fields:
    #             for field, value in unique_fields.items():
    #                 if (
    #                     db.query(self.model)
    #                     .filter(getattr(self.model, field) == value)
    #                     .filter(self.model.id != db_obj.id)  # Exclude current record
    #                     .first()
    #                 ):
    #                     raise HTTPException(
    #                         status_code=400,
    #                         detail=f"Update conflict: {field}='{value}' matches another record.",
    #                     )

    #         obj_data = obj_in.dict(exclude_unset=True)
    #         for field, value in obj_data.items():
    #             setattr(db_obj, field, value)
    #         db.commit()
    #         db.refresh(db_obj)

    #         # Handle file upload if provided
    #         if file:
    #             file_info = self.upload_to_gcs(file)
    #             file_entry = self.file_model(
    #                 file_name=file_info["file_name"],
    #                 file_path=file_info["file_path"],
    #                 uploaded_by_id=db_obj.updated_by,
    #                 organization_id=obj_data.get("organization_id"),
    #                 record_id=db_obj.id,
    #             )
    #             db.add(file_entry)
    #             db.commit()

    #         self.audit_action(db, "update", self.model.__tablename__, db_obj.id, db_obj.updated_by)
    #         return db_obj
    #     except IntegrityError as e:
    #         db.rollback()
    #         self.log_error(e, "update")
    #         raise HTTPException(status_code=400, detail="Database integrity error.")
    #     except Exception as e:
    #         self.log_error(e, "update")
    #         raise HTTPException(status_code=500, detail="Internal server error")

    # ------------------- UPDATED UPDATE FUNCTION -------------------
    def update(
        self,
        db: Session,
        reference: Dict[str, Any],
        obj_in: Any,  # a Pydantic model instance
        unique_fields: Optional[Dict] = None,
        file: Optional[UploadFile] = None,
    ) -> Any:
        """
        Update an object by reference.
        
        Requirements:
        - For models with employee_id or organization_id, ensure that such a field is available either
        from the payload or from the existing record.
        - Supports partial (or full) updates.
        - Ensures that unique fields are either unchanged or do not conflict with another record.
        """
        try:
            db_obj = self.resolve_reference(db, reference)
            obj_data = obj_in.dict(exclude_unset=True)

            # --- Validate Required Identification Field ---
            if hasattr(self.model, "employee_id"):
                # For models like EmploymentHistory, AcademicQualification, etc.
                employee_id = obj_data.get("employee_id") or getattr(db_obj, "employee_id", None)
                if not employee_id:
                    raise HTTPException(status_code=400, detail="employee_id is required for this update.")
                # Optionally, you might validate that the employee exists and retrieve its organization_id:
                # employee = db.query(Employee).filter(Employee.id == employee_id).first()
                # if not employee:
                #     raise HTTPException(status_code=404, detail="Associated employee not found.")
            elif hasattr(self.model, "organization_id"):
                # For models like User, Organization, etc.
                organization_id = obj_data.get("organization_id") or getattr(db_obj, "organization_id", None)
                if not organization_id:
                    raise HTTPException(status_code=400, detail="organization_id is required for this update.")

            # --- Unique Field Check (only if the new value differs) ---
            if unique_fields:
                for field, new_value in unique_fields.items():
                    current_value = getattr(db_obj, field, None)
                    # Only check uniqueness if the value is changing
                    if new_value != current_value:
                        existing = (
                            db.query(self.model)
                            .filter(getattr(self.model, field) == new_value)
                            .filter(self.model.id != db_obj.id)
                            .first()
                        )
                        if existing:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Update conflict: {field}='{new_value}' matches another record."
                            )

            # --- Apply the update (supports partial updates) ---
            for field, value in obj_data.items():
                setattr(db_obj, field, value)
            db.commit()
            db.refresh(db_obj)

            # --- Handle File Upload if Provided ---
            if file:
                file_info = self.upload_to_gcs(file)
                # Create a file storage entry (if file_model is defined)
                file_entry = self.file_model(
                    file_name=file_info["file_name"],
                    file_path=file_info["file_path"],
                    uploaded_by_id=getattr(db_obj, "updated_by", None),
                    organization_id=obj_data.get("organization_id") or getattr(db_obj, "organization_id", None),
                    record_id=db_obj.id,
                    record_type=self.model.__tablename__
                )
                db.add(file_entry)
                db.commit()
            asyncio.create_task(push_summary_update(db, str(obj_data.get("organization_id"))))
            self.audit_action(db, "update", self.model.__tablename__, db_obj.id, getattr(db_obj, "updated_by", None))
            return db_obj

        except IntegrityError as e:
            db.rollback()
            self.log_error(e, "update")
            raise HTTPException(status_code=400, detail="Database integrity error.")
        except Exception as e:
            self.log_error(e, "update")
            raise HTTPException(status_code=500, detail="Internal server error")
    


    # def delete(
    #     self,
    #     db: Session,
    #     reference: Dict[str, Any],
    #     soft_delete: bool = False,
    #     force_delete: bool = False,
    #     dependent_model: Optional[Any] = None,
    #     dependent_field: Optional[str] = None,
    #     user_id: Optional[UUID] = None,
    # ) -> Any:
    #     """
    #     Delete an object by reference (primary key, unique field, or indexed field).
    #     """
    #     try:
    #         obj = self.resolve_reference(db, reference)

    #         # Check for dependent data if a dependent model and field are provided
    #         if dependent_model and dependent_field:
    #             is_dependent = (
    #                 db.query(exists().where(getattr(dependent_model, dependent_field) == obj.id))
    #                 .scalar()
    #             )
    #             if is_dependent:
    #                 if not force_delete:
    #                     if soft_delete and hasattr(self.model, "is_active"):
    #                         obj.is_active = False
    #                         db.commit()
    #                         self.audit_action(db, "soft_delete", self.model.__tablename__, obj.id, user_id)
    #                         return {"message": f"Soft delete applied to record."}
    #                     raise HTTPException(
    #                         status_code=400,
    #                         detail="Cannot delete record due to referential integrity violations.",
    #                     )

    #         db.delete(obj)
    #         db.commit()
    #         self.audit_action(db, "delete", self.model.__tablename__, obj.id, user_id)
    #         return {"message": f"Record deleted successfully."}
    #     except IntegrityError as e:
    #         db.rollback()
    #         self.log_error(e, "delete")
    #         raise HTTPException(
    #             status_code=400,
    #             detail="Deletion failed due to database constraints or referential integrity violations.",
    #         )
    #     except Exception as e:
    #         self.log_error(e, "delete")
    #         raise HTTPException(status_code=500, detail="Internal server error")



    # ------------------- UPDATED DELETE FUNCTION -------------------
    def delete(
        self,
        db: Session,
        reference: Dict[str, Any],
        soft_delete: bool = False,
        force_delete: bool = False,
        user_id: Optional[UUID] = None,
    ) -> Any:
        """
        Delete an object by reference.
        
        Requirements:
        - Automatically check dependent relationships (via SQLAlchemy inspection).
        - If dependent records exist and force_delete is False, then:
            * If soft_delete is enabled and the model supports it (has an is_active field), perform a soft delete.
            * Otherwise, raise an error.
        - Prior to deletion, check for file URL fields (e.g. profile_image_path, image_path, certificate_path, etc.)
        and attempt to remove the corresponding file from Google Cloud Storage.
        """
        try:
            obj = self.resolve_reference(db, reference)

            # --- Dynamically Check for Dependent Relationships ---
            mapper = inspect(self.model)
            for rel in mapper.relationships:
                # If the relationship does not have cascade delete (or delete-orphan) enabled,
                # then check if there are any dependent rows.
                if not any(cascade in rel.cascade for cascade in ("delete", "all, delete-orphan")):
                    related_items = getattr(obj, rel.key)
                    if related_items:
                        if not force_delete:
                            if soft_delete and hasattr(obj, "is_active"):
                                obj.is_active = False
                                db.commit()
                                self.audit_action(db, "soft_delete", self.model.__tablename__, obj.id, user_id)
                                return {"message": "Soft delete applied to record due to dependent data."}
                            raise HTTPException(
                                status_code=400,
                                detail=f"Cannot delete record due to dependent data in relationship: {rel.key}"
                            )

            # --- File Cleanup: Find any columns that store file URLs ---
            file_field_names = [
                col.name for col in self.model.__table__.columns
                if isinstance(col.type, String) and "path" in col.name
            ]
            gcs = GoogleCloudStorage(settings.BUCKET_NAME)
            for field in file_field_names:
                file_url = getattr(obj, field, None)
                if file_url and isinstance(file_url, str) and "storage.googleapis.com" in file_url:
                    try:
                        gcs.delete_from_gcs(file_url)
                    except Exception as e:
                        self.log_error(e, f"delete_from_gcs for field {field}")
                        # Continue even if file deletion fails

            # --- Delete the Object ---
            db.delete(obj)
            db.commit()
            # push_summary_update(db, obj.id)
            asyncio.create_task(push_summary_update(db, obj.id))
            self.audit_action(db, "delete", self.model.__tablename__, obj.id, user_id)
            return {"message": "Record deleted successfully."}

        except IntegrityError as e:
            db.rollback()
            self.log_error(e, "delete")
            raise HTTPException(
                status_code=400,
                detail="Deletion failed due to database constraints or referential integrity violations."
            )
        except Exception as e:
            self.log_error(e, "delete")
            raise HTTPException(status_code=500, detail="Internal server error")



    def bulk_create(self, db: Session, obj_list: List[BaseModel], unique_fields: Optional[List[str]] = None, user_id: Optional[UUID] = None) -> List[Any]:
        """Create multiple records in bulk."""
        created_objects = []
        try:
            for obj_in in obj_list:
                # Check for duplicates
                if unique_fields:
                    for field in unique_fields:
                        if db.query(self.model).filter(getattr(self.model, field) == getattr(obj_in, field)).first():
                            raise HTTPException(
                                status_code=400,
                                detail=f"Duplicate entry detected for {field}='{getattr(obj_in, field)}'.",
                            )
                obj_data = obj_in.dict()
                obj_data["created_by"] = user_id
                db_obj = self.model(**obj_data)
                db.add(db_obj)
                created_objects.append(db_obj)
            db.commit()

            # Audit bulk creation
            self.audit_action(db, "bulk_create", self.model.__tablename__, None, user_id)
        except IntegrityError as e:
            db.rollback()
            self.log_error(e, "bulk_create")
            raise HTTPException(status_code=400, detail="Bulk creation failed due to database integrity errors.")
        except Exception as e:
            db.rollback()
            self.log_error(e, "bulk_create")
            raise HTTPException(status_code=500, detail="Internal server error")
        return created_objects

    def upload_data(
        self, db: Session, file: UploadFile, unique_fields: Optional[List[str]] = None, user_id: Optional[UUID] = None
    ) -> Dict:
        """Upload data from a CSV or Excel file."""
        if file.content_type not in ["application/vnd.ms-excel", "text/csv"]:
            raise HTTPException(
                status_code=400, detail="Only CSV files are supported for data upload."
            )
        try:
            content = file.file.read()
            if file.content_type == "application/vnd.ms-excel":
                data = pd.read_excel(io.BytesIO(content))
            else:
                data = pd.read_csv(io.StringIO(content.decode("utf-8")))

            for index, row in data.iterrows():
                row_data = row.to_dict()
                # Validate uniqueness
                if unique_fields:
                    for field in unique_fields:
                        if db.query(self.model).filter(getattr(self.model, field) == row_data[field]).first():
                            raise HTTPException(
                                status_code=400,
                                detail=f"Duplicate entry for {field}='{row_data[field]}' in row {index + 1}.",
                            )
                # Insert into database
                row_data["created_by"] = user_id
                db_obj = self.model(**row_data)
                db.add(db_obj)
            db.commit()

            # Audit data upload
            self.audit_action(db, "upload_data", self.model.__tablename__, None, user_id)
        except Exception as e:
            db.rollback()
            self.log_error(e, "upload_data")
            raise HTTPException(status_code=400, detail=f"Data upload failed: {str(e)}")
        return {"message": "Data uploaded successfully."}