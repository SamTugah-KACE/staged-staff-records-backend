import json
from sqlalchemy.dialects.postgresql import  JSONB
from sqlalchemy.orm import  Session
from sqlalchemy.exc import SQLAlchemyError
from database.db_session import BaseModel
from Models.models import DataBank
import logging
from datetime import datetime
from fastapi import FastAPI, APIRouter, Depends, HTTPException, BackgroundTasks, Query, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from uuid import UUID 
from typing import Any, Dict, List, Optional
from database.db_session import get_db  # Your database session dependency
from Crud.crud import CRUDBase as crud # Generic CRUD class
from Models.models import DataBank  # Import your models
from Schemas.schemas import DataBankSchema, DataCreateBankSchema  # Import your Pydantic schemas
from Utils.config import ProductionConfig  # Import your settings



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = ProductionConfig()


def create_default(db: Session, seed_data: Optional[List[str]] = None) -> None:
    """
    Dynamically seeds default roles and permissions into the DataBank table.
    
    If seed_data is not provided, it uses both defaults:
      - DEFAULT_PERMISSIONS (a list of strings)
      - DEFAULT_ROLE_PERMISSIONS (a list of dicts, each with "name" and "permissions")
    
    For each seed type, the function checks if an entry already exists:
      - If not, it creates a new entry.
      - If it exists, it appends any unique data based on the type:
          * For "permissions": performs a union of permission strings.
          * For "roles": checks the 'name' field of each role and appends new roles only.
    
    Raises a RuntimeError if seeding fails.
    """
    # Default seed types if not provided
    if not seed_data:
        seed_data = ["permissions", "roles"]

    # Define handlers for each seed type.
    seed_handlers: Dict[str, Dict[str, Any]] = {
        "permissions": {
            "data_name": "permissions",
            "data": settings.DEFAULT_PERMISSIONS
        },
        "roles": {
            "data_name": "roles",
            "data": settings.DEFAULT_ROLE_PERMISSIONS
        }
    }

    try:
        with db.begin():  # Begin a transaction
            # Iterate through each seed type and process accordingly.
            for seed in seed_data:
                seed_info = seed_handlers.get(seed)
                if not seed_info:
                    logger.warning(f"Seed type '{seed}' is not recognized. Skipping.")
                    continue

                data_name = seed_info["data_name"]
                incoming_data = seed_info["data"]

                # Fetch existing entry by data_name.
                entry = db.query(DataBank).filter_by(data_name=data_name).first()

                if not entry:
                    entry = DataBank(data_name=data_name, data=incoming_data)
                    db.add(entry)
                    logger.info(f"Created new DataBank entry for '{data_name}'.")
                else:
                    # Merge new data with existing while ensuring uniqueness.
                    if isinstance(entry.data, list) and isinstance(incoming_data, list):
                        if data_name == "roles":
                            # For roles: merge by role "name".
                            existing_names = {item.get("name") for item in entry.data if isinstance(item, dict)}
                            new_items = [item for item in incoming_data if item.get("name") not in existing_names]
                            if new_items:
                                entry.data.extend(new_items)
                                logger.info(f"Appended {len(new_items)} new roles to '{data_name}'.")
                        elif data_name == "permissions":
                            # For permissions: perform a union of permission strings.
                            existing_items = set(entry.data)
                            new_items = set(incoming_data) - existing_items
                            if new_items:
                                entry.data = list(existing_items.union(new_items))
                                logger.info(f"Appended {len(new_items)} new permissions to '{data_name}'.")
                        else:
                            logger.warning(f"Unrecognized data structure for '{data_name}'. Skipping.")
                    else:
                        logger.warning(f"Incompatible data format in existing entry '{data_name}'.")

        logger.info("Default seed data created or updated successfully.")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during seeding: {str(e)}")
        raise RuntimeError("Seeding default data failed. Please check the logs.") from e



app = APIRouter()



from sqlalchemy.ext.mutable import MutableList

@app.post("/data-bank/", response_model=DataCreateBankSchema, status_code=status.HTTP_201_CREATED)
async def create_data_bank(
    data_name: str = Form(...),
    data: str = Form(...),  # Accept JSON string from form data
    db: Session = Depends(get_db),
):
    """
    Dynamic API to create or update entries in the DataBank table.
    Ensures uniqueness for incoming data and appends to existing data if the data_name exists.
    If the data_name does not exist, it creates a new entry.
    """
    try:
        # Parse `data` string into a dictionary or list
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid data format. Expected a valid JSON string.",
            )

        # Ensure parsed_data is a list for uniform processing
        if not isinstance(parsed_data, list):
            parsed_data = [parsed_data]

        # Fetch the databank entry for the given data_name
        databank_entry = db.query(DataBank).filter(DataBank.data_name == data_name).first()

        if databank_entry:
            # Debugging: Ensure data is correctly initialized
            if databank_entry.data is None:
                databank_entry.data = []

            # Debugging: Check data types and contents
            logger.debug(f"Existing data: {databank_entry.data}")
            logger.debug(f"New data: {parsed_data}")

            # Append only unique entries to the existing data
            def dict_to_tuple(d):
                return tuple(sorted((k, dict_to_tuple(v) if isinstance(v, dict) else v) for k, v in d.items()))

            existing_set = {dict_to_tuple(entry) for entry in databank_entry.data}
            new_data = [
                item for item in parsed_data
                if dict_to_tuple(item) not in existing_set
            ]

            logger.debug(f"Unique new data to append: {new_data}")

            if new_data:
                databank_entry.data.extend(new_data)
                db.commit()
                logger.info(f"Appended new data to existing data_name '{data_name}'.")
            else:
                logger.info(f"No new unique data to append for data_name '{data_name}'.")
        else:
            # Create a new entry if the data_name does not exist
            databank_entry = DataBank(data_name=data_name, data=parsed_data)
            db.add(databank_entry)
            db.commit()
            logger.info(f"Created new data_name '{data_name}' with initial data.")

        # Refresh and return the updated or newly created entry
        db.refresh(databank_entry)
        return DataCreateBankSchema(data_name=databank_entry.data_name, data=databank_entry.data)

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process the request. Please try again later.",
        )







@app.get("/fetch-all/", response_model=List[DataBankSchema])
def read_banks(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """
    List all default data
    """
    data = crud(DataBank)
    return data.get_multi(db, skip=skip, limit=limit)



@app.put("/data-bank/update/", response_model=DataCreateBankSchema, status_code=status.HTTP_200_OK)
async def update_data_bank(
    identifier: str = Form(...),  # Accept `data_name` or `id`
    key: str = Form(...),         # Key to identify the specific entry
    value: str = Form(...),       # Value of the key to match the specific entry
    data: str = Form(...),        # New data to update
    db: Session = Depends(get_db),
):
    """
    Dynamically update a specific entry in the DataBank based on `data_name` or `id`.
    Uses a provided key and value to locate the target entry in the `data` list.
    """
    try:
        # Parse the new data
        try:
            new_entry = json.loads(data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid data format. Expected a valid JSON string.",
            )

        if not isinstance(new_entry, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid input: Expected a single dictionary for the new data.",
            )

        # Find the databank entry using `data_name` or `id`
        databank_entry = (
            db.query(DataBank)
            .filter(
                (DataBank.data_name == identifier) | (DataBank.id == identifier)
            )
            .first()
        )

        if not databank_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="DataBank entry not found.",
            )

        # Find the index of the entry with the matching key-value pair
        existing_data = databank_entry.data
        index_to_update = next(
            (i for i, entry in enumerate(existing_data) if entry.get(key) == value),
            None
        )

        if index_to_update is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entry with `{key}`='{value}' not found.",
            )

        # Update the entry
        existing_data[index_to_update] = new_entry
        databank_entry.data = existing_data
        db.commit()
        db.refresh(databank_entry)

        return DataCreateBankSchema(data_name=databank_entry.data_name, data=databank_entry.data)

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the data. Please try again later.",
        )
