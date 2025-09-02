import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from fastapi import HTTPException, BackgroundTasks, UploadFile, Depends
from typing import Type, TypeVar, Optional, List, Any
from pydantic import BaseModel
from uuid import UUID 
from datetime import datetime
from passlib.context import CryptContext
import secrets
from smtplib import SMTPException
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import logging
from Service.email_service import build_account_email_html, EmailService
from Service.gcs_service import GoogleCloudStorage
from Utils.config import DevelopmentConfig, get_config
from email_service import *
from Service.file_service import upload_file
# logging.basicConfig(level=logging.DEBUG)
from Schemas.schemas import *
from sqlalchemy.orm import joinedload
from Utils.serialize_4_json import serialize_for_json
import json 
from Utils.security import pwd_context, Security
from Utils.util import get_organization_acronym, extract_items
from Utils.config import DevelopmentConfig
from Utils.sms_utils import get_sms_service



settings = ProductionConfig()


# Initialize the global Security instance.
# In a multi-tenant system sharing one schema, a common secret key is often used.
global_security = Security(secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM, token_expire_minutes=60)



# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define generic types
ModelType = TypeVar("ModelType")  # SQLAlchemy model
SchemaType = TypeVar("SchemaType", bound=BaseModel)  # Pydantic schema
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)  # Pydantic create schema


# Constants for Random Username and Password Generation
CHARACTER_SET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ012345679"
USERNAME_LENGTH = 8
PASSWORD_LENGTH = 12


# Helper function to generate random string
def generate_random_string(length: int) -> str:
    return ''.join(secrets.choice(CHARACTER_SET) for _ in range(length))


class CRUDBase:
    """
    Generic CRUD class for managing database operations with SQLAlchemy models and Pydantic schemas.
    """

    def __init__(self, model: Type[ModelType]):
        """
        Initialize the CRUD class with a model.

        :param model: SQLAlchemy model
        """
        self.model = model
    
    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def get(
        self, db: Session, id: UUID
    ) -> Optional[ModelType]:
        """
        Retrieve a single record by its ID.

        :param db: Database session
        :param id: Record ID
        :return: Single record or None
        """
        db_obj = db.query(self.model).filter(self.model.id == id).first()
        if db_obj:
            return OrganizationSchema.model_validate(db_obj)  # Convert to Pydantic schema
        return None


    def get_multi(
        self, db: Session, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """
        Retrieve multiple records with optional pagination.

        :param db: Database session
        :param skip: Number of records to skip
        :param limit: Maximum number of records to return
        :return: List of records
        """
        try:
            return db.query(self.model).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Database error occurred: {str(e)}"
            )


    def create(
        self, db: Session, obj_in: CreateSchemaType, created_by: Optional[UUID] = None
    ) -> ModelType:
        """
        Create a new record in the database.

        :param db: Database session
        :param obj_in: Data to create the record
        :param created_by: Optional ID of the creator
        :return: Newly created record
        """
        obj_data = obj_in.dict(exclude_unset=True)
        if created_by:
            obj_data["created_by"] = created_by

        db_obj = self.model(**obj_data)
        db.add(db_obj)
        try:
            db.commit()
            db.refresh(db_obj)
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Integrity error occurred: {str(e.orig)}"
            )
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error occurred: {str(e)}"
            )
        return db_obj

    def update(
        self, db: Session, db_obj: ModelType, obj_in: Any, updated_by: Optional[UUID] = None
    ) -> ModelType:
        """
        Update an existing record in the database.

        :param db: Database session
        :param db_obj: Existing database object
        :param obj_in: Data to update the record
        :param updated_by: Optional ID of the updater
        :return: Updated record
        """
        obj_data = obj_in.dict(exclude_unset=True) if isinstance(obj_in, BaseModel) else obj_in
        if updated_by:
            obj_data["updated_by"] = updated_by

        for field, value in obj_data.items():
            setattr(db_obj, field, value)

        try:
            db.commit()
            db.refresh(db_obj)
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Integrity error occurred: {str(e.orig)}"
            )
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error occurred: {str(e)}"
            )
        return db_obj

    def delete(self, db: Session, id: UUID) -> ModelType:
        """
        Delete a record from the database.

        :param db: Database session
        :param id: Record ID
        :return: Deleted record
        """
        obj = self.get(db, id)
        if not obj:
            raise HTTPException(status_code=404, detail="Record not found")
        db.delete(obj)
        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error occurred: {str(e)}"
            )
        return obj
    

    


    def log_audit(self, db: Session, action: str, table_name: str, record_id: UUID, performed_by: Optional[UUID]):
        """
        Logs an action in the AuditLog table.

        :param db: Database session
        :param action: Action performed (e.g., CREATE, UPDATE, DELETE)
        :param table_name: Name of the table affected
        :param record_id: ID of the record affected
        :param performed_by: User ID who performed the action
        """
        audit_log = AuditLog(
            action=action,
            table_name=table_name,
            record_id=record_id,
            performed_by=performed_by,
        )
        db.add(audit_log)
        db.commit()



    async def create_with_nested(
        self,
        background_tasks: BackgroundTasks,
        db: Session,
        obj_in: CreateSchemaType,
        created_by: Optional[UUID] = None,
        # sms_svc: object = Depends(get_sms_service)
    ) -> ModelType:
        


        obj_data = obj_in.dict(exclude_unset=True)

        # Assign created_by and populate BaseModel columns
        if created_by:
            obj_data["created_by"] = created_by

        # Generate dynamic organization URL
        # obj_data["access_url"] = f"https://{obj_data['name'].lower().replace(' ', '-')}.myapp.com"
        
        # slug = f"{obj_data['name'].lower().replace(' ', '-')}-{Security.generate_random_char()}"
        ab = get_organization_acronym(obj_data['name']).lower()
        print("\n\nabbr.: ", ab)
        slug = f"{ab}-{Security.generate_random_char(8)}"
        # obj_data["access_url"] = f"http://localhost:8000/{slug}"

        obj_data["access_url"] = f"{settings.TENANT_URL}/{slug}"

        existing_org = db.query(Organization).filter(Organization.name == obj_data["name"].strip()).first()
        if existing_org:
            raise HTTPException(
                status_code=400,
                detail="Organization Already Exists",
            )
        
        existing_org_mail = db.query(Organization).filter(Organization.org_email == obj_data["org_email"].strip()).first()
        if existing_org_mail:
            raise HTTPException(
                status_code=400,
                detail="Organizational Email Address Already Used",
            )
        

        
        


        try:
            
                    
            # Insert the main object (e.g., Organization)
            db_obj = self.model(**{k: v for k, v in obj_data.items() if k not in ["roles", "employees", "users", "tenancies", "settings"]})
            
            #Insert Employee
            if "employees" in obj_data:
                for employee_data in obj_data["employees"]:
                    
                    if not employee_data["first_name"].strip():
                        raise HTTPException(status_code=400, detail="First Name Required!")
                    
                    if not employee_data["last_name"].strip():
                        raise HTTPException(status_code=400, detail="Last Name Required!")
                    
                    if not employee_data["email"].strip():
                        raise HTTPException(status_code=400, detail="Employee Email Required!")
                    
                    
                    
                    #check if employee email, contact_info and other unique data  already exists
                    isEmailExist = db.query(Employee).filter(Employee.email == employee_data["email"]).first()
                    if isEmailExist:
                        raise HTTPException(status_code=400, detail="User Email Already Exist")
                    
                    if "contact_info" in employee_data and "phone" in employee_data["contact_info"]:
                        isPhoneExist = db.query(Employee).filter(Employee.contact_info["phone"].astext == employee_data["contact_info"]["phone"]).first()
                        if isPhoneExist:
                            raise HTTPException(status_code=400, detail="User Phone Already Exist")
                    elif "contact_info" in employee_data and "contact" in employee_data["contact_info"]:
                        isPhoneExist = db.query(Employee).filter(Employee.contact_info["phone"].astext == employee_data["contact_info"]["phone"]).first()
                        if isPhoneExist:
                            raise HTTPException(status_code=400, detail="User Phone Already Exist")
                    
                
            
            
            
            db.add(db_obj)
            

            # existing_emp_mail = db.query(Employee).filter(Employee.email == "email" in obj_data["employees"].strip(), Organization.id == db_obj.id).first()
            # if existing_emp_mail:
            #     raise HTTPException(
            #         status_code=400,
            #         detail="Employee Email Address Already Used",
            #     )
            
            db.commit()
            db.refresh(db_obj)
            

            # Insert Roles and map their IDs
            role_map = {}
            first_role_id = None
            if "roles" in obj_data:
                for role_data in obj_data["roles"]:
                    role_data["organization_id"] = db_obj.id
                    role_obj = Role(**role_data)
                    db.add(role_obj)
                    db.commit()
                    db.refresh(role_obj)
                    role_map[role_data["name"]] = role_obj.id

                    if not first_role_id:
                        first_role_id = role_obj.id

            
            


                    print()
                
                

                

            # Insert Users
            if "users" in obj_data:
                for user_data in obj_data["users"]:
                    # Resolve role_id if the user specifies a role name
                    if "role_id" not in user_data and "role_name" in user_data:
                        role_name = user_data.pop("role_name", None)
                        if role_name and role_name in role_map:
                            user_data["role_id"] = role_map[role_name]
                            
                    else:
                        # Resolve role_id if missing
                        user_data["role_id"] = first_role_id
                    
                
                  
                    # Generate email, username and password if not provided
                    # user_data["email"] = user_data.get("email") if user_data.get("email").strip() else employee_data["email"]
                    user_data["email"] = employee_data["email"].strip()
                    # username = user_data.get("username", "").strip() or generate_random_string()
                    username = employee_data["email"].strip() or  employee_data["first_name"].strip() + "-" + generate_random_string(4)
                    password = user_data.get("hashed_password", "").strip() or  generate_random_string(12)
                    hashed_password = self.hash_password(password)
                    
                    
                    user_obj = User(
                        username=username,
                        email=user_data["email"],
                        hashed_password=hashed_password,
                        role_id=user_data["role_id"],
                        organization_id=db_obj.id,
                        image_path= user_data.get("image_path", "https://example.com/default-profile.png"),
                        created_by=id,
                    )
                    user_obj.created_by = user_obj.id
                    db.add(user_obj)
                    

                    employee_data["created_by"] = user_obj.id
                    employee_obj = Employee(
                        organization_id=db_obj.id,
                        # profile_image_path= employee_data.get("profile_image_path", "https://example.com/default-profile.png")
                    **{k: v for k, v in employee_data.items() if k != "organization_id"},
                        
                    )
                    # setattr(employee_obj, "_role_id", user_data["role_id"])
                    # setattr(employee_obj, "_plain_password", password)
                    # setattr(employee_obj, "_user_image",user_data.get("image_path", "https://example.com/default-profile.png"))
                    db.add(employee_obj)
                
                    
                    

                    # Log the creation of the organization
                    self.log_audit(db, "CREATE", self.model.__tablename__, db_obj.id,  user_obj.id)

                    # Log role creation
                    self.log_audit(db, "CREATE", "roles", role_obj.id, created_by or user_obj.id)

                    # Log the creation of the employee data
                    self.log_audit(db, "CREATE", "employees", employee_obj.id, created_by or user_obj.id)

                    # Log user creation
                    self.log_audit(db, "CREATE", "users", user_obj.id, created_by or user_obj.id)

                    org_dict = {
                        "title": employee_data["title"] if "title" in employee_data else "",
                        "first_name": employee_data["first_name"],
                        "last_name": employee_data["last_name"],
                        "email": employee_data["email"],
                        "org_name": obj_data["name"],
                    }
                    signin_page = obj_data["access_url"]+"/signin"
                    print("signin page: ", signin_page)

                    logos = obj_data["logos"]
                    logo = next(iter(logos.values())) if len(logos) > 1 else logos



                    email_service = EmailService()  # Instantiate the email service
                    # Send email with credentials
                    email_body = build_account_email_html(org_dict, extract_items(logo), signin_page, password)
                    # email_body = get_email_template(username, password, signin_page, obj_data['name'] )
                    await email_service.send_email(background_tasks, recipients=[user_data["email"]], subject="Account Credentials", html_body=email_body)

                   # Call External API for Facial Authentication Username Update
                    # if user_data["image_path"]:
                    #     async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    #         form = aiohttp.FormData()
                    #         form.add_field("new_username", username)
                    #         form.add_field("file", user_data["image_path"], filename="image.jpg", content_type="image/jpeg")

                    #         try:
                    #             async with session.put(f"{settings.FACIAL_AUTH_API_URL}/update/{user_obj.username}", data=form) as response:
                    #                 if response.status == 502:
                    #                     logger.warning(f"External API deployment issue detected: {response.status}. Issue is with the API, not the request.")
                    #                 elif response.status != 200:
                    #                     raise HTTPException(status_code=500, detail="Failed to update facial authentication system.")
                    #         except asyncio.TimeoutError:
                    #             logger.warning("External API timeout. Please try again.")
                                # raise HTTPException(status_code=504, detail="External API timeout. Please try again.")
                        
            created_by = user_obj.id if user_obj else created_by

            

            # Insert Tenancies and Terms and Conditions
            if "tenancies" in obj_data:
                for tenancy_data in obj_data["tenancies"]:
                    # Handle terms and conditions
                    if "terms_and_conditions" in tenancy_data:
                        for terms_data in tenancy_data["terms_and_conditions"]:
                            terms_obj = TermsAndConditions(**terms_data)
                            terms_obj.created_by = user_obj.id
                            db.add(terms_obj)
                            db.commit()
                            db.refresh(terms_obj)
                            tenancy_data["terms_and_conditions_id"] = terms_obj.id

                            # Log terms creation
                            self.log_audit(db, "CREATE", "terms_and_conditions", terms_obj.id, created_by)

                        del tenancy_data["terms_and_conditions"]
                
                            
                tenancy_obj = Tenancy(
                    organization_id=db_obj.id,
                    **{k: v for k, v in tenancy_data.items() if k != "organization_id"},
                )
                tenancy_obj.created_by = user_obj.id
                db.add(tenancy_obj)
                db.commit()  # Ensure the tenancy object is committed
                db.refresh(tenancy_obj)  # Refresh to populate the ID

                # Log tenancy creation
                self.log_audit(db, "CREATE", "tenancies", tenancy_obj.id, created_by)
            
            if "settings" in obj_data:
                 for settings_data in obj_data["settings"]:
                    #  if settings_data:
                    settings_obj = SystemSetting(
                    organization_id=db_obj.id,
                    **{k: v for k, v in settings_data.items() if k != "organization_id"},
                )
                    settings_obj.created_by = user_obj.id
                    db.add(settings_obj)
                    db.commit()  # Ensure the System object is committed
                    db.refresh(settings_obj)  # Refresh to populate the ID
                        # Log terms creation
                    self.log_audit(db, "CREATE", "settings", settings_obj.id, created_by)

            db.commit()





            # Reload the organization with nested relationships
            db_obj = (
                db.query(self.model)
                .options(
                    joinedload(self.model.roles),
                    joinedload(self.model.employees),
                    joinedload(self.model.users),
                    joinedload(self.model.tenancies),
                    joinedload(self.model.settings),
                )
                .filter_by(id=db_obj.id)
                .first()
            )

             # schedule SMS per employee
            # for emp in employee_data:
            #     phone = emp.get("contact_info", {}).get("phone")
            #     contact = emp.get("contact_info", {}).get("contact")

            #     if phone or contact:
            #         background_tasks.add_task(
            #             sms_svc.send,
            #             phone or contact,
            #             "org_signup",
            #             {"first_name": emp["first_name"], "org_name": name}
            #         )


            return OrganizationSchema.model_validate(db_obj)

        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Integrity error occurred: {str(e.orig)}",
            )
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error occurred: {str(e)}",
            )
        

    def match_related_record(self, db: Session, model: Type, data: Dict, primary_key: UUID) -> Optional[Any]:
        """
        Matches an existing record in the related model based on partial data.
        """
        if not model:
            raise ValueError("Related model is None. Ensure relationships are correctly configured.")

        query = db.query(model).filter(getattr(model, "organization_id", None) == primary_key)
        for key, value in data.items():
            if key in model.__table__.columns.keys():
                query = query.filter(getattr(model, key) == value)
        return query.first()

    def is_data_unique(self, db: Session, model: Any, data: dict, exclude_id: Optional[UUID] = None) -> bool:
        """
        Checks if the given data is unique within the specified model's table.

        Args:
            db (Session): The database session.
            model (Any): The SQLAlchemy model to query.
            data (dict): The incoming data to check for uniqueness.
            exclude_id (Optional[UUID]): ID of the row to exclude from uniqueness validation.

        Returns:
            bool: True if the data is unique, False otherwise.
        """
        logger.debug("Validating uniqueness for data: %s in model: %s", data, model.__tablename__)

        # Prepare the query
        query = db.query(model)

        # Check each key-value pair in the incoming data
        for key, value in data.items():
            if key in model.__table__.columns:  # Ensure the key exists in the model's table
                query = query.filter(getattr(model, key) == value)

        # Exclude the current row from the query if exclude_id is provided
        if exclude_id:
            query = query.filter(model.id != exclude_id)

        # Check if any rows match the query
        exists = db.query(query.exists()).scalar()

        if exists:
            logger.debug(
                "Duplicate data detected in model '%s': %s", model.__tablename__, data
            )
            return False  # Not unique
        return True  # Unique


    
    # def update_with_nested(self, db: Session, db_obj: ModelType, obj_in: Any, updated_by: Optional[UUID] = None) -> ModelType:
    #     """
    #     Updates an object and its nested relationships while ensuring:
    #     - Proper handling of deeply nested relationships (e.g., terms_and_conditions in tenancies).
    #     - Validation and injection of referential keys (e.g., id, organization_id).
    #     - Efficient and clean handling of database operations.
    #     """
    #     logger.info("Starting update_with_nested for object: %s", db_obj)

    #     try:
    #         parent_id = getattr(db_obj, "id", None)
    #         if not parent_id:
    #             raise HTTPException(status_code=400, detail="Parent ID is required but missing.")

    #         obj_data = obj_in.dict(exclude_unset=True) if isinstance(obj_in, BaseModel) else obj_in
    #         logger.debug("Parsed input data: %s", obj_data)

    #         def handle_nested_relationships(relationship_field, data, parent_id):
    #             """
    #             Handles nested relationships (e.g., tenancies, terms_and_conditions) efficiently.
    #             """
    #             related_model = db_obj.__mapper__.relationships[relationship_field].mapper.class_
    #             current_relationship = getattr(db_obj, relationship_field, [])
    #             existing_records_map = {str(obj.id): obj for obj in current_relationship if hasattr(obj, "id")}

    #             updated_records = []
    #             for item in data:
    #                 if "id" in item and item["id"] in existing_records_map:
    #                     # Update existing record
    #                     existing_record = existing_records_map[item["id"]]
    #                     for key, val in item.items():
    #                         if getattr(existing_record, key, None) != val:
    #                             setattr(existing_record, key, val)
    #                     updated_records.append(existing_record)
    #                 else:
    #                     # Create new record
    #                     item["organization_id"] = parent_id
    #                     new_record = related_model(**item)
    #                     db.add(new_record)
    #                     updated_records.append(new_record)

    #                 # Handle deeply nested relationships (e.g., terms_and_conditions)
    #                 if "terms_and_conditions" in item:
    #                     terms_model = related_model.__mapper__.relationships["terms_and_conditions"].mapper.class_
    #                     terms_data = item.pop("terms_and_conditions", [])
    #                     for terms_item in terms_data:
    #                         terms_item["organization_id"] = parent_id
    #                         if "id" not in terms_item or not terms_item["id"]:
    #                             matched_terms = self.match_related_record(db, terms_model, terms_item, parent_id)
    #                             if matched_terms:
    #                                 terms_item["id"] = str(matched_terms.id)
    #                         new_terms = terms_model(**terms_item)
    #                         db.add(new_terms)

    #             # Clear existing relationships and update with new records
    #             current_relationship.clear()
    #             current_relationship.extend(updated_records)

    #         for field, value in obj_data.items():
    #             if field in db_obj.__mapper__.relationships:
    #                 if isinstance(value, list):
    #                     handle_nested_relationships(field, value, parent_id)
    #                 elif isinstance(value, dict):
    #                     # Handle one-to-one relationships
    #                     related_model = db_obj.__mapper__.relationships[field].mapper.class_
    #                     existing_relation = getattr(db_obj, field, None)
    #                     if existing_relation:
    #                         for key, val in value.items():
    #                             if getattr(existing_relation, key, None) != val:
    #                                 setattr(existing_relation, key, val)
    #                     else:
    #                         value["organization_id"] = parent_id
    #                         new_relation = related_model(**value)
    #                         db.add(new_relation)
    #                         setattr(db_obj, field, new_relation)
    #             elif field in db_obj.__mapper__.c.keys():  # Handle scalar fields
    #                 if value is not None:
    #                     setattr(db_obj, field, value)

    #         if updated_by:
    #             db_obj.updated_by = updated_by

    #         db.commit()
    #         db.refresh(db_obj)
    #         logger.info("Successfully updated object: %s", db_obj)

    #         return db_obj

    #     except IntegrityError as e:
    #         db.rollback()
    #         logger.error("Integrity error during update_with_nested: %s", str(e))
    #         raise HTTPException(status_code=400, detail=f"Integrity error occurred: {str(e.orig)}")
    #     except SQLAlchemyError as e:
    #         db.rollback()
    #         logger.error("Database error during update_with_nested: %s", str(e))
    #         raise HTTPException(status_code=500, detail=f"Database error occurred: {str(e)}")
    #     except Exception as e:
    #         db.rollback()
    #         logger.exception("Unexpected error during update_with_nested.")
    #         raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


    def update_with_nested(self, db: Session, db_obj: ModelType, obj_in: Any, updated_by: Optional[UUID] = None) -> ModelType:
        """
        Updates an object and its nested relationships while:
        - Avoiding accidental insertions when the row to update is ambiguous.
        - Leveraging organization_id or unique fields to infer rows for update.
        - Automatically injecting missing organization_id or id in nested models.
        - Logging all changes in an audit log.
        """
        logger.info("Starting update_with_nested for object: %s", db_obj)

        try:
            parent_id = getattr(db_obj, "id", None)
            if not parent_id:
                raise HTTPException(status_code=400, detail="Parent ID is required but missing.")

            obj_data = obj_in.dict(exclude_unset=True) if isinstance(obj_in, BaseModel) else obj_in
            logger.debug("Parsed input data: %s", obj_data)

            updated_fields = []  # Track updated fields for audit logging

            def inject_referential_keys(data, model, parent_id):
                """
                Inject organization_id or infer row id into the nested payload based on model schema.
                """
                if "organization_id" not in data:
                    if hasattr(model, "organization_id"):
                        data["organization_id"] = str(parent_id)

                if "id" not in data or not data["id"]:
                    matched_record = self.match_related_record(db, model, data, parent_id)
                    if matched_record:
                        data["id"] = str(matched_record.id)
                    else:
                        logger.warning(f"Ambiguous data detected: {data}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unable to determine the specific row for {model.__tablename__}. Please ensure the data is not ambiguous.",
                        )

            def handle_nested_relationships(relationship_field, data, parent_id):
                """
                Handles nested relationships efficiently and recursively.
                """
                related_model = db_obj.__mapper__.relationships[relationship_field].mapper.class_
                current_relationship = getattr(db_obj, relationship_field, [])
                existing_records_map = {str(obj.id): obj for obj in current_relationship if hasattr(obj, "id")}

                updated_records = []
                for item in data:
                    if not isinstance(item, dict):
                        raise HTTPException(status_code=400, detail=f"Invalid data for {relationship_field}: {item}")

                    inject_referential_keys(item, related_model, parent_id)

                    if "id" in item and item["id"] in existing_records_map:
                        existing_record = existing_records_map[item["id"]]
                        for key, val in item.items():
                            if key in ("username", "hashed_password"):  # Exclude sensitive fields
                                continue
                            if getattr(existing_record, key, None) != val:
                                setattr(existing_record, key, val)
                                updated_fields.append(f"{relationship_field}.{key}")
                        updated_records.append(existing_record)
                    else:
                        # Create new record if ambiguity is resolved
                        new_record = related_model(**item)
                        db.add(new_record)
                        updated_records.append(new_record)

                    # Handle deeply nested relationships (e.g., terms_and_conditions)
                    if relationship_field == "tenancies" and "terms_and_conditions" in item:
                        handle_deeply_nested_relationship(item["terms_and_conditions"], related_model, parent_id)

                current_relationship.clear()
                current_relationship.extend(updated_records)

            def handle_deeply_nested_relationship(nested_data, parent_model, parent_id):
                """
                Handles deeply nested relationships (e.g., terms_and_conditions under tenancies).
                """
                nested_model = parent_model.__mapper__.relationships["terms_and_conditions"].mapper.class_
                for nested_item in nested_data:
                    if not isinstance(nested_item, dict):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid nested data for terms_and_conditions: {nested_item}",
                        )

                    inject_referential_keys(nested_item, nested_model, parent_id)
                    new_nested_record = nested_model(**nested_item)
                    db.add(new_nested_record)

            for field, value in obj_data.items():
                if field in db_obj.__mapper__.relationships:  # Handle relationships
                    if isinstance(value, list):  # One-to-many relationships
                        handle_nested_relationships(field, value, parent_id)
                    elif isinstance(value, dict):  # One-to-one relationships
                        related_model = db_obj.__mapper__.relationships[field].mapper.class_
                        existing_relation = getattr(db_obj, field, None)
                        inject_referential_keys(value, related_model, parent_id)

                        if existing_relation:
                            for key, val in value.items():
                                if key in ("username", "hashed_password"):
                                    continue
                                if getattr(existing_relation, key, None) != val:
                                    setattr(existing_relation, key, val)
                                    updated_fields.append(f"{field}.{key}")
                        else:
                            new_relation = related_model(**value)
                            db.add(new_relation)
                            setattr(db_obj, field, new_relation)
                elif field in db_obj.__mapper__.c.keys():  # Scalar fields
                    if value is not None:
                        if field == "logos":  # JSONB field
                            setattr(db_obj, field, value)
                            updated_fields.append(field)
                        elif field == "image_path":
                            setattr(db_obj, field, value)
                            updated_fields.append(field)
                        elif getattr(db_obj, field, None) != value:
                            setattr(db_obj, field, value)
                            updated_fields.append(field)

            if updated_by:
                db_obj.updated_by = updated_by

            db.commit()
            db.refresh(db_obj)
            logger.info("Successfully updated object: %s", db_obj)

            for field in updated_fields:
                self.log_audit(
                    db,
                    action="UPDATE",
                    table_name=self.model.__tablename__,
                    record_id=db_obj.id,
                    performed_by=updated_by,
                )

            return db_obj

        except IntegrityError as e:
            db.rollback()
            logger.error("Integrity error during update_with_nested: %s", str(e))
            raise HTTPException(status_code=400, detail=f"Integrity error occurred: {str(e.orig)}")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error("Database error during update_with_nested: %s", str(e))
            raise HTTPException(status_code=500, detail=f"Database error occurred: {str(e)}")
        except Exception as e:
            db.rollback()
            logger.exception("Unexpected error during update_with_nested.")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
































    ##### user fields resolved
    # def update_with_nested(self, db: Session, db_obj: ModelType, obj_in: Any, updated_by: Optional[UUID] = None) -> ModelType:
    #     """
    #     Updates an object and its nested relationships while preserving existing data
    #     and avoiding modifications to fields like 'username' or 'hashed_password'.
    #     """
    #     logger.info("Starting update_with_nested for object: %s", db_obj)

    #     try:
    #         # Parse incoming data
    #         obj_data = obj_in.dict(exclude_unset=True) if isinstance(obj_in, BaseModel) else obj_in
    #         logger.debug("Parsed input data: %s", obj_data)

    #         updated_fields = []  # Track updated fields for auditing

    #         for field, value in obj_data.items():
    #             logger.debug("Processing field '%s' with value: %s", field, value)

    #             if field in db_obj.__mapper__.relationships.keys():  # Handle relationships
    #                 related_model = db_obj.__mapper__.relationships[field].mapper.class_
    #                 logger.debug("Identified relationship for field '%s' with related model: %s", field, related_model)

    #                 if isinstance(value, list):  # Handle one-to-many or many-to-many relationships
    #                     current_relationship = getattr(db_obj, field, [])
    #                     logger.debug("Current relationship for field '%s': %s", field, current_relationship)

    #                     existing_records_map = {str(obj.id): obj for obj in current_relationship if hasattr(obj, 'id')}
    #                     updated_records = []

    #                     for item in value:
    #                         if "id" in item and item["id"] in existing_records_map:
    #                             # Update existing record
    #                             existing_record = existing_records_map[item["id"]]
    #                             for key, val in item.items():
    #                                 if key in ("username", "hashed_password"):
    #                                     logger.debug("Skipping update for field '%s' as it is immutable.", key)
    #                                     continue
    #                                 if getattr(existing_record, key, None) != val:
    #                                     setattr(existing_record, key, val)
    #                                     updated_fields.append(f"{field}.{key}")
    #                             updated_records.append(existing_record)
    #                         else:
    #                             # Ignore new record creation during updates
    #                             logger.warning("Ignoring new record creation for '%s'. Updates only modify existing data.", field)

    #                     # Replace relationship records
    #                     current_relationship.clear()
    #                     current_relationship.extend(updated_records)

    #                 elif isinstance(value, dict):  # Handle one-to-one relationships
    #                     existing_relation = getattr(db_obj, field, None)
    #                     if existing_relation:
    #                         for key, val in value.items():
    #                             if key in ("username", "hashed_password"):
    #                                 logger.debug("Skipping update for field '%s' as it is immutable.", key)
    #                                 continue
    #                             if getattr(existing_relation, key, None) != val:
    #                                 setattr(existing_relation, key, val)
    #                                 updated_fields.append(f"{field}.{key}")
    #                     else:
    #                         logger.warning("Skipping new relation creation for '%s'. Updates only modify existing data.", field)

    #             elif field == "logos":  # Handle logos upload
    #                 if value:
    #                     logger.debug("Updating logos field with value: %s", value)
    #                     setattr(db_obj, field, value)

    #             else:  # Update scalar fields
    #                 if getattr(db_obj, field, None) != value:
    #                     setattr(db_obj, field, value)
    #                     updated_fields.append(field)

    #         # Add audit fields
    #         if updated_by:
    #             db_obj.updated_by = updated_by

    #         # Commit changes
    #         db.commit()
    #         db.refresh(db_obj)
    #         logger.info("Successfully updated object: %s", db_obj)

    #         # Audit logging
    #         for field in updated_fields:
    #             self.log_audit(
    #                 db,
    #                 action="UPDATE",
    #                 table_name=self.model.__tablename__,
    #                 record_id=db_obj.id,
    #                 performed_by=updated_by,
    #             )

    #         return db_obj

    #     except IntegrityError as e:
    #         db.rollback()
    #         logger.error("Integrity error during update_with_nested: %s", str(e))
    #         raise HTTPException(status_code=400, detail=f"Integrity error occurred: {str(e.orig)}")
    #     except SQLAlchemyError as e:
    #         db.rollback()
    #         logger.error("Database error during update_with_nested: %s", str(e))
    #         raise HTTPException(status_code=500, detail=f"Database error occurred: {str(e)}")
    #     except Exception as e:
    #         db.rollback()
    #         logger.exception("Unexpected error during update_with_nested.")
    #         raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")




    
 

    






















    # def update_with_nested(
    #     self, db: Session, db_obj: ModelType, obj_in: Any, updated_by: Optional[UUID] = None
    # ) -> ModelType:
    #     """
    #     Update an existing record along with optional nested models and file uploads.

    #     :param db: Database session
    #     :param db_obj: Existing database object
    #     :param obj_in: Data to update the record
    #     :param updated_by: Optional ID of the updater
    #     :return: Updated record
    #     """
    #     if isinstance(obj_in, BaseModel):
    #         obj_data = obj_in.dict(exclude_unset=True)
    #     else:
    #         obj_data = obj_in

    #     # Handle file uploads for logos
    #     if "logos" in obj_data and isinstance(obj_data["logos"], UploadFile):
    #         gcs_client = GoogleCloudStorage(GCS_BUCKET_NAME)
    #         logo_file = obj_data["logos"]
    #         uploaded_logo_url = gcs_client.upload_to_gcs(
    #             files=[{"filename": logo_file.filename, "content": logo_file.file.read()}],
    #             folder=f"organizations/{db_obj.name}/logos/",
    #         )[0]
    #         obj_data["logos"] = uploaded_logo_url

    #     # Validate uniqueness for nested models
    #     for field, values in obj_data.items():
    #         if field in db_obj.__mapper__.relationships.keys():
    #             related_model = db_obj.__mapper__.relationships[field].mapper.class_

    #             for item in values:
    #                 # Skip checking if the value is the same as the existing row
    #                 if "id" in item and item["id"]:
    #                     existing_row = (
    #                         db.query(related_model).filter(related_model.id == item["id"]).first()
    #                     )
    #                     if existing_row:
    #                         continue

    #                 # Check for conflicts with other rows in the database
    #                 conflict = (
    #                     db.query(related_model)
    #                     .filter_by(**{k: v for k, v in item.items() if k != "id"})
    #                     .first()
    #                 )
    #                 if conflict:
    #                     raise HTTPException(
    #                         status_code=400,
    #                         detail=f"Conflict detected in {field}: {item}. "
    #                         "This value already exists in another record.",
    #                     )

    #             # Update or create nested records
    #             updated_related_records = []
    #             for related_data in values:
    #                 if "id" in related_data:
    #                     existing = (
    #                         db.query(related_model)
    #                         .filter_by(id=related_data["id"])
    #                         .first()
    #                     )
    #                     if existing:
    #                         for key, value in related_data.items():
    #                             setattr(existing, key, value)
    #                         updated_related_records.append(existing)
    #                 else:
    #                     new_record = related_model(**related_data)
    #                     updated_related_records.append(new_record)
    #             setattr(db_obj, field, updated_related_records)
    #         else:
    #             setattr(db_obj, field, values)

    #     # Set updated_by if provided
    #     if updated_by:
    #         db_obj.updated_by = updated_by

    #     try:
    #         db.commit()
    #         db.refresh(db_obj)
    #     except IntegrityError as e:
    #         db.rollback()
    #         raise HTTPException(
    #             status_code=400, detail=f"Integrity error occurred: {str(e.orig)}"
    #         )
    #     except SQLAlchemyError as e:
    #         db.rollback()
    #         raise HTTPException(
    #             status_code=500, detail=f"Database error occurred: {str(e)}"
    #         )

    #     return db_obj

    



    def delete_with_references(self, db: Session, id: UUID, confirm: bool, performed_by: Optional[UUID] = None) -> None:
        """
        Deletes a record and its related references if confirmed, with audit logging.

        :param db: Database session
        :param id: Record ID
        :param confirm: Confirmation flag for cascading deletion
        :param performed_by: User ID performing the operation (for audit logging)
        """
        # Fetch the database object using the model class
        db_obj = db.query(self.model).filter(self.model.id == id).first()
        if not db_obj:
            raise HTTPException(status_code=404, detail="Record not found")

        # Check related records
        related_counts = {
            relationship.key: db.query(relationship.mapper.class_).filter(relationship.primaryjoin).count()
            for relationship in db_obj.__mapper__.relationships
        }

        logger.info(f"Related records found: {related_counts}")

        # If there are related records, confirm deletion
        if any(related_counts.values()):
            if not confirm:
                raise HTTPException(
                    status_code=400,
                    detail=f"Record has related references: {related_counts}. Pass `confirm=True` to cascade delete.",
                )

        try:
            # Perform cascading deletion for related records if confirm is True
            if confirm:
                for relationship_key, count in related_counts.items():
                    if count > 0:
                        related_query = db.query(
                            db_obj.__mapper__.relationships[relationship_key].mapper.class_
                        ).filter(db_obj.__mapper__.relationships[relationship_key].primaryjoin)
                        related_records = related_query.all()

                        # Delete related records
                        for related_record in related_records:
                            db.delete(related_record)

                            # Log deletion of each related record
                            self.log_audit(
                                db,
                                action="DELETE",
                                table_name=db_obj.__mapper__.relationships[relationship_key].mapper.class_.__tablename__,
                                record_id=related_record.id,
                                performed_by=performed_by,
                            )
                        logger.info(f"Deleted related records for: {relationship_key} (Count: {count})")

            # Log deletion of the main record
            self.log_audit(
                db,
                action="DELETE",
                table_name=self.model.__tablename__,
                record_id=id,
                performed_by=performed_by,
            )

            # Delete the main record
            db.delete(db_obj)
            db.commit()
            logger.info(f"Successfully deleted record with ID: {id}")

        except IntegrityError as e:
            db.rollback()
            logger.error(f"Integrity error during deletion: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Integrity error occurred: {str(e.orig)}")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Database error during deletion: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Database error occurred: {str(e)}")
        except Exception as e:
            db.rollback()
            logger.exception("Unexpected error during deletion.")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")




    def create_organization(
        self,
        db: Session,
        obj_in: CreateSchemaType,
        created_by: Optional[UUID] = None,
        email_smtp_config: dict = None,
    ) -> ModelType:
        """Custom create method for organizations."""


        obj_data = obj_in.dict(exclude_unset=True)
        if created_by:
            obj_data["created_by"] = created_by

        # Convert nested dictionaries to SQLAlchemy model instances
        for key, value in obj_data.items():
            if isinstance(value, list) and key in self.model.__mapper__.relationships.keys():
                related_model = self.model.__mapper__.relationships[key].mapper.class_
                obj_data[key] = [related_model(**item) for item in value if isinstance(item, dict)]

    

        # Generate dynamic organization URL
        obj_data["access_url"] = f"https://{obj_data['name'].lower().replace(' ', '-')}.myapp.com"

        # Create the organization
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        try:
            db.commit()
            db.refresh(db_obj)

            # Create related records
            self.setup_organization_related_records(db, db_obj, obj_in)

            # Create the first admin user
            self.create_admin_user(db, db_obj, obj_in, email_smtp_config)

        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Integrity error occurred: {str(e.orig)}",
            )
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error occurred: {str(e)}",
            )

        return db_obj
    

    def setup_organization_related_records(self, db: Session, organization, obj_data):
        """
        Sets up dashboards, tenancies, and other related records for the organization.

        :param db: Database session
        :param organization: Created organization instance
        :param obj_data: Original data for creating the organization
        """
        # Setup default dashboard
        dashboard = Dashboard(
            dashboard_name="Main Dashboard",
            dashboard_data={"widgets": ["Welcome Widget", "Stats"]},
            access_url=f"{organization.access_url}/dashboard",
            organization_id=organization.id,
        )
        db.add(dashboard)

        # Setup default tenancy if none provided
        if not obj_data.get("tenancies"):
            tenancy = Tenancy(
                organization_id=organization.id,
                start_date=datetime.utcnow().date(),
                billing_cycle="Monthly",
                status="Active",
            )
            db.add(tenancy)

        # Setup default terms and conditions
        terms = TermsAndConditions(
            title="Default Terms",
            content={"agreement": "Sample terms content"},
            version="1.0",
            is_active=True,
        )
        db.add(terms)

        db.commit()





    def create_admin_user(self, db: Session, organization, obj_data, email_smtp_config):
        """
        Creates an admin user for the organization.

        :param db: Database session
        :param organization: Created organization instance
        :param obj_data: Original data for creating the organization
        :param email_smtp_config: SMTP settings for sending emails
        """
        # Generate a random username and password
        username = generate_random_string(USERNAME_LENGTH)
        password = generate_random_string(PASSWORD_LENGTH)
        hashed_password = self.hash_password(password)

        # Create the admin user
        user = User(
            username=username,
            email=obj_data["email"],
            hashed_password=hashed_password,
            organization_id=organization.id,
            role_id=None,  # Optionally assign a default admin role
        )
        db.add(user)

        try:
            db.commit()
            db.refresh(user)

            # Send email with credentials
            self.send_credentials_email(
                smtp_config=email_smtp_config,
                to_email=obj_data["email"],
                username=username,
                password=password,
            )
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Integrity error occurred while creating user: {str(e.orig)}",
            )
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error occurred while creating user: {str(e)}",
            )


    def send_credentials_email(self, smtp_config, to_email, username, password):
        """Sends an email with login credentials."""
        if not smtp_config:
            raise HTTPException(
                status_code=500,
                detail="SMTP configuration is not provided.",
            )

        msg = MIMEText(
            f"Welcome to the system!\n\nYour login credentials are:\nUsername: {username}\nPassword: {password}\n\nPlease change your password after logging in."
        )
        msg["Subject"] = "Welcome to the System"
        msg["From"] = smtp_config["from_email"]
        msg["To"] = to_email

        try:
            with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
                server.starttls()
                server.login(smtp_config["username"], smtp_config["password"])
                server.send_message(msg)

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send email: {str(e)}",
            )


# Example Usage with Models
from Models.Tenants.organization import Organization, Tenancy, TermsAndConditions
from Models.Tenants.role import  Role
from Models.models import *  # Replace with your actual model imports

# Instantiate CRUD classes for models
organization_crud = CRUDBase(Organization)
role_crud = CRUDBase(Role)
user_crud = CRUDBase(User)
