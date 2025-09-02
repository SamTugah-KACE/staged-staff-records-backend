import uuid
from fastapi import HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import exists, or_, and_
from typing import List, Any, Optional, Dict, Union
from pydantic import BaseModel
from uuid import UUID
import pandas as pd
import io
from google.cloud import storage
import logging
from sqlalchemy.inspection import inspect
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import sessionmaker






# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants for Google Cloud Storage
GCS_BUCKET_NAME = "your_bucket_name"
GCS_BASE_URL = "https://storage.googleapis.com"


# Standardized Response Schemas
class SuccessResponse(BaseModel):
    message: str
    data: Optional[Any] = None

# Standardized Response Schemas
class StandardResponse(BaseModel):
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class CRUDBase:
    def __init__(self, model, audit_model=None, file_model=None):
        self.model = model
        self.audit_model = audit_model
        self.file_model = file_model

    def log_error(self, error: Exception, operation: str):
        """Log errors for debugging and auditing purposes."""
        logger.error(f"Error during {operation}: {str(error)}")

    async def audit_action(
        self,
        db: AsyncSession,
        action: str,
        table_name: str,
        record_id: Union[UUID, None],
        user_id: Optional[UUID] = None,
    ):
        """Log an action to the audit log."""
        if self.audit_model:
            audit_entry = self.audit_model(
                action=action, table_name=table_name, record_id=record_id, performed_by=user_id
            )
            db.add(audit_entry)
            await db.commit()

    async def upload_to_gcs(self, file: UploadFile) -> Dict:
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


    async def upload_multiple_to_gcs(self, files: List[UploadFile]) -> List[Dict]:
        """Upload multiple files to Google Cloud Storage."""
        uploaded_files = []
        for file in files:
            try:
                file_info = await self.upload_to_gcs(file)
                uploaded_files.append(file_info)
            except Exception as e:
                self.log_error(e, "upload_multiple_to_gcs")
                raise HTTPException(status_code=500, detail="Failed to upload some files")
        return uploaded_files


    # async def resolve_reference(self, db: AsyncSession, reference: Dict[str, Any]) -> Any:
    #     """
    #     Resolve the object reference using primary key, unique, or indexed fields.
    #     :param reference: Dictionary containing the reference field and value.
    #     :return: Object matching the reference or raises 404.
    #     """
    #     query = db.query(self.model)
    #     filters = [getattr(self.model, field) == value for field, value in reference.items()]
    #     obj = await query.filter(or_(*filters)).first()
    #     if not obj:
    #         raise HTTPException(status_code=404, detail="Item not found with the given reference.")
    #     return obj
    
    async def resolve_reference(self, db: AsyncSession, reference: Dict[str, Any]) -> Any:
        """Resolve the object reference using primary key, unique, or indexed fields."""
        if not isinstance(db, AsyncSession):
            logger.error(f"Expected db to be AsyncSession, got {type(db)} instead")
            raise HTTPException(status_code=500, detail="Database session is not valid.")

        try:
            filters = [getattr(self.model, field) == value for field, value in reference.items()]
            query = select(self.model).where(or_(*filters))
            result = await db.execute(query)
            obj = result.scalar_one_or_none()
            if not obj:
                logger.error("Item not found for reference: %s", reference)
                raise HTTPException(status_code=404, detail="Item not found with the given reference.")
            return obj
        except HTTPException:
            raise  # Propagate HTTP exceptions as-is
        except Exception as e:
            self.log_error(e, "resolve_reference")
            raise HTTPException(status_code=500, detail="Error resolving reference.")

    


    def apply_filters(self, query, filters: Dict) -> Any:
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
            else:
                filter_conditions.append(getattr(self.model, field) == condition)
        return query.filter(and_(*filter_conditions))
    

    async def get(self, db: AsyncSession, reference: Dict[str, Any]) -> Any:
        """Get a single object by reference."""
        try:
           
            obj = await self.resolve_reference(db, reference)
             
            # Retrieve associated files if file_model is defined
            if self.file_model:
                query = select(self.file_model).where(self.file_model.record_id == obj.id)
                result = await db.execute(query)
                obj.files = result.scalars().all()

            # Audit the read action
            if self.audit_model:
                audit_entry = self.audit_model(
                    action="read", table_name=self.model.__tablename__, record_id=obj.id
                )
                db.add(audit_entry)
                await db.commit()
            return StandardResponse(message="Record retrieved successfully.", data=obj)
            # return SuccessResponse(message="Record retrieved successfully.", data=obj)
        except HTTPException as e:
        # Log and re-raise HTTP exceptions for proper response codes
            self.log_error(e, "get")
            raise
        except Exception as e:
            # Catch unexpected errors and log them as 500 errors
            self.log_error(e, "get")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def get_multi(
        self, db: AsyncSession, filters: Optional[Dict] = None, skip: int = 0, limit: int = 10
    ) -> List[Any]:
        """Get multiple objects with optional filters."""
        try:
            # query = db.query(self.model)
            query = select(self.model)
            if filters:
                query = self.apply_filters(query, filters)
                # for field, value in filters.items():
                #     query = query.filter(getattr(self.model, field) == value)

            # objs = await query.offset(skip).limit(limit).all()

            query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            objs = result.scalars().all()


            # Retrieve associated files for each object
            if self.file_model:
                for obj in objs:
                    # files = await db.query(self.file_model).filter(self.file_model.record_id == obj.id).all()
                    # obj.files = files
                    query = select(self.file_model).where(self.file_model.record_id == obj.id)
                    result = await db.execute(query)
                    obj.files = result.scalars().all()

            await self.audit_action(db, "read_multi", self.model.__tablename__, None)
            # return SuccessResponse(message="Records retrieved successfully.", data=objs)
            return StandardResponse(message="Records retrieved successfully.", data=objs)

        except Exception as e:
            self.log_error(e, "get_multi")
            raise HTTPException(status_code=500, detail="Internal server error")


    

    


    async def create(
        self,
        db: AsyncSession,
        obj_in: BaseModel,
        unique_fields: Optional[List[str]] = None,
        user_id: Optional[UUID] = None,
        file: Optional[UploadFile] = None,
    ) -> Any:
        """
        Generic create function for any model, dynamically handling relationships, constraints, and nested data.
        """
        try:
            # Convert Pydantic model to dictionary
            obj_data = obj_in.dict(exclude_unset=True)

            # Use SQLAlchemy mapper to inspect the model's columns and relationships
            mapper = inspect(self.model)
            valid_columns = {column.key for column in mapper.columns}
            valid_relationships = {rel.key: rel.mapper.class_ for rel in mapper.relationships}

            # Separate main object data and nested data
            main_obj_data = {key: value for key, value in obj_data.items() if key in valid_columns}
            nested_data = {key: value for key, value in obj_data.items() if key in valid_relationships}

            async with db.begin_nested():  # Ensure atomicity
                # Step 1: Handle unique constraints
                if unique_fields:
                    for field in unique_fields:
                        query = select(self.model).where(getattr(self.model, field) == main_obj_data.get(field))
                        result = await db.execute(query)
                        if result.scalar_one_or_none():
                            raise HTTPException(
                                status_code=400,
                                detail=f"An entry with {field}='{main_obj_data.get(field)}' already exists.",
                            )

                # Step 2: Insert main object
                db_obj = self.model(**main_obj_data)
                if "created_by" in valid_columns:
                    db_obj.created_by = user_id
                db.add(db_obj)

                # Step 3: Handle nested relationships
                for rel_field, rel_items in nested_data.items():
                    related_model = valid_relationships[rel_field]
                    if not isinstance(rel_items, list):
                        rel_items = [rel_items]  # Ensure consistency

                    for item in rel_items:
                        if isinstance(item, dict):
                            # Handle foreign key constraints
                            parent_id_field = f"{self.model.__name__.lower()}_id"
                            if parent_id_field in inspect(related_model).columns:
                                item[parent_id_field] = getattr(db_obj, "id", None)

                            # Check if related table is empty
                            query = select(func.count(related_model.id))
                            result = await db.execute(query)
                            if result.scalar_one() == 0:
                                # Insert default related data if table is empty
                                default_data = related_model(**item)
                                db.add(default_data)
                            else:
                                # Validate foreign key relationships
                                filters = [getattr(related_model, key) == value for key, value in item.items()]
                                query = select(related_model).where(and_(*filters))
                                result = await db.execute(query)
                                if not result.scalar_one_or_none():
                                    raise HTTPException(
                                        status_code=400,
                                        detail=f"Related data for {rel_field} does not exist and cannot be validated.",
                                    )

                            related_obj = related_model(**item)
                            db.add(related_obj)

                # Step 4: Commit the transaction
                await db.commit()
                await db.refresh(db_obj)

                # Step 5: Handle file upload (if applicable)
                if file and hasattr(self.model, "file_model"):
                    file_info = await self.upload_to_gcs(file)
                    file_entry = self.file_model(
                        file_name=file_info["file_name"],
                        file_path=file_info["file_path"],
                        uploaded_by_id=user_id,
                        organization_id=getattr(db_obj, "id", None),
                        record_id=db_obj.id,
                    )
                    db.add(file_entry)
                    await db.commit()

                # Step 6: Log audit action
                await self.audit_action(db, "create", self.model.__tablename__, db_obj.id, user_id)

                return StandardResponse(message="Record created successfully.", data=db_obj)

        except IntegrityError as e:
            await db.rollback()
            self.log_error(e, "create")
            raise HTTPException(status_code=400, detail="Database integrity error.")
        except Exception as e:
            await db.rollback()
            self.log_error(e, "create")
            raise HTTPException(status_code=500, detail=str(e))




    async def update(
    self,
    db: AsyncSession,
    reference: Dict[str, Any],
    obj_in: BaseModel,
    unique_fields: Optional[List[str]] = None,
    file: Optional[UploadFile] = None,
    user_id: Optional[UUID] = None,
    ) -> Any:
        """
        Update an object by reference.
        :param reference: Dictionary containing the reference field and value.
        :param obj_in: Data for updating the object.
        :param unique_fields: List of fields to enforce uniqueness constraints during update.
        :param file: Optional file to upload and associate with the updated object.
        :param user_id: ID of the user performing the update.
        """
        try:
            db_obj = await self.resolve_reference(db, reference)

            # Validate uniqueness for specified fields
            if unique_fields:
                for field in unique_fields:
                    if (
                        await db.query(self.model)
                        .filter(getattr(self.model, field) == getattr(obj_in, field))
                        .filter(self.model.id != db_obj.id)  # Exclude current record
                        .first()
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Update conflict: {field}='{getattr(obj_in, field)}' matches another record.",
                        )

            # Apply updates
            obj_data = obj_in.dict(exclude_unset=True)
            for field, value in obj_data.items():
                setattr(db_obj, field, value)
            await db.commit()
            await db.refresh(db_obj)

            # Handle file upload if provided
            if file:
                file_info = await self.upload_to_gcs(file)
                file_entry = self.file_model(
                    file_name=file_info["file_name"],
                    file_path=file_info["file_path"],
                    uploaded_by_id=user_id,
                    organization_id=obj_data.get("organization_id"),
                    record_id=db_obj.id,
                )
                db.add(file_entry)
                await db.commit()

            # Audit the update action
            await self.audit_action(db, "update", self.model.__tablename__, db_obj.id, user_id)
            return SuccessResponse(message="Record updated successfully.", data=db_obj)
        except IntegrityError as e:
            await db.rollback()
            self.log_error(e, "update")
            raise HTTPException(status_code=400, detail="Database integrity error.")
        except Exception as e:
            await db.rollback()
            self.log_error(e, "update")
            raise HTTPException(status_code=500, detail="Internal server error")


    async def delete(
    self,
    db: AsyncSession,
    reference: Dict[str, Any],
    soft_delete: bool = False,
    force_delete: bool = False,
    dependent_model: Optional[Any] = None,
    dependent_field: Optional[str] = None,
    user_id: Optional[UUID] = None,
     ) -> Any:
        """
        Delete an object by reference.
        :param reference: Dictionary containing the reference field and value.
        :param soft_delete: Whether to perform a soft delete.
        :param force_delete: Whether to force delete even with dependent records.
        :param dependent_model: Model to check for dependent records.
        :param dependent_field: Field in the dependent model referencing this object.
        :param user_id: ID of the user performing the delete.
        """
        try:
            db_obj = await self.resolve_reference(db, reference)

            # Check for dependent data if a dependent model and field are provided
            if dependent_model and dependent_field:
                is_dependent = (
                    await db.query(exists().where(getattr(dependent_model, dependent_field) == db_obj.id))
                    .scalar()
                )
                if is_dependent:
                    if not force_delete:
                        if soft_delete and hasattr(self.model, "is_active"):
                            db_obj.is_active = False
                            await db.commit()
                            await self.audit_action(db, "soft_delete", self.model.__tablename__, db_obj.id, user_id)
                            return SuccessResponse(message="Soft delete applied to record.")
                        raise HTTPException(
                            status_code=400,
                            detail="Cannot delete record due to referential integrity violations.",
                        )

            await db.delete(db_obj)
            await db.commit()
            await self.audit_action(db, "delete", self.model.__tablename__, db_obj.id, user_id)
            return SuccessResponse(message="Record deleted successfully.")
        except IntegrityError as e:
            await db.rollback()
            self.log_error(e, "delete")
            raise HTTPException(
                status_code=400,
                detail="Deletion failed due to database constraints or referential integrity violations.",
            )
        except Exception as e:
            await db.rollback()
            self.log_error(e, "delete")
            raise HTTPException(status_code=500, detail="Internal server error")



    async def bulk_create(
        self, db: AsyncSession, obj_list: List[BaseModel], unique_fields: Optional[List[str]] = None, user_id: Optional[UUID] = None
    ) -> List[Any]:
        """Bulk create records."""
        try:
            objects = []
            for obj_in in obj_list:
                if unique_fields:
                    for field in unique_fields:
                        if await db.query(self.model).filter(getattr(self.model, field) == getattr(obj_in, field)).first():
                            raise HTTPException(
                                status_code=400,
                                detail=f"Duplicate entry detected for {field}='{getattr(obj_in, field)}'.",
                            )
                obj_data = obj_in.dict()
                obj_data["created_by"] = user_id
                objects.append(self.model(**obj_data))

            await db.bulk_save_objects(objects)
            await db.commit()

            await self.audit_action(db, "bulk_create", self.model.__tablename__, None, user_id)
            return SuccessResponse(message="Bulk records created successfully.", data=objects)
        except IntegrityError as e:
            await db.rollback()
            self.log_error(e, "bulk_create")
            raise HTTPException(status_code=400, detail="Bulk creation failed due to database integrity errors.")
        except Exception as e:
            await db.rollback()
            self.log_error(e, "bulk_create")
            raise HTTPException(status_code=500, detail="Internal server error")
        


    async def upload_data(
        self,
        db: AsyncSession,
        file: UploadFile,
        unique_fields: Optional[List[str]] = None,
        user_id: Optional[UUID] = None,
    ) -> Dict:
        """
        Upload data from a CSV or Excel file.
        :param db: Database session.
        :param file: File to upload (CSV or Excel).
        :param unique_fields: List of fields to enforce uniqueness during upload.
        :param user_id: ID of the user performing the upload.
        :return: Success message.
        """
        if file.content_type not in ["application/vnd.ms-excel", "text/csv"]:
            raise HTTPException(
                status_code=400, detail="Only CSV or Excel files are supported for data upload."
            )
        try:
            content = file.file.read()
            if file.content_type == "application/vnd.ms-excel":
                data = pd.read_excel(io.BytesIO(content))
            else:
                data = pd.read_csv(io.StringIO(content.decode("utf-8")))

            bulk_objects = []
            for index, row in data.iterrows():
                row_data = row.to_dict()

                # Validate uniqueness
                if unique_fields:
                    for field in unique_fields:
                        if await db.query(self.model).filter(getattr(self.model, field) == row_data[field]).first():
                            raise HTTPException(
                                status_code=400,
                                detail=f"Duplicate entry for {field}='{row_data[field]}' in row {index + 1}.",
                            )

                row_data["created_by"] = user_id
                bulk_objects.append(self.model(**row_data))

            # Perform bulk save
            await db.bulk_save_objects(bulk_objects)
            await db.commit()

            # Audit data upload
            await self.audit_action(db, "upload_data", self.model.__tablename__, None, user_id)
            return SuccessResponse(message="Data uploaded successfully.")
        except Exception as e:
            await db.rollback()
            self.log_error(e, "upload_data")
            raise HTTPException(status_code=400, detail=f"Data upload failed: {str(e)}")

