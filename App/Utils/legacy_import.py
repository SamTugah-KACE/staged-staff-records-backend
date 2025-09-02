import pandas as pd
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from fastapi import UploadFile
from typing import List, Any
import io



def import_legacy_data(file_path: str, table_name: str, db_engine, models):
    """
    Imports legacy data from a file into the specified table.
    :param file_path: Path to the data file (CSV/XLSX/SQL).
    :param table_name: Target table name in the database.
    :param db_engine: SQLAlchemy database engine.
    :param models: Dictionary of SQLAlchemy models.
    """
    try:
        # Detect file type and read data
        if file_path.endswith('.csv'):
            data = pd.read_csv(file_path)
        elif file_path.endswith('.xlsx'):
            data = pd.read_excel(file_path)
        elif file_path.endswith('.sql'):
            with open(file_path, 'r') as f:
                sql_commands = f.read()
            with db_engine.connect() as conn:
                conn.execute(sql_commands)
            print(f"SQL file {file_path} executed successfully.")
            return
        else:
            raise ValueError("Unsupported file type. Use CSV, XLSX, or SQL files.")

        # Inspect database schema
        inspector = inspect(db_engine)
        columns_in_db = [col['name'] for col in inspector.get_columns(table_name)]

        # Check for new columns
        data_columns = set(data.columns)
        missing_columns = data_columns - set(columns_in_db)
        extra_columns = set(columns_in_db) - data_columns

        if missing_columns:
            print(f"New columns detected: {missing_columns}. Adding them dynamically.")
            for col in missing_columns:
                # Dynamically add new columns to the table
                with db_engine.connect() as conn:
                    conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {col} TEXT')

        # Ensure all columns in the dataframe are present in the database
        data = data[list(data_columns & set(columns_in_db))]

        # Insert or update data
        with Session(db_engine) as session:
            Model = models.get(table_name)
            if not Model:
                raise ValueError(f"Model for table {table_name} not found.")

            for _, row in data.iterrows():
                record = session.query(Model).filter_by(id=row.get('id')).first()
                if record:
                    for col in data.columns:
                        setattr(record, col, row[col])
                else:
                    session.add(Model(**row.to_dict()))

            session.commit()
        print(f"Data imported successfully into {table_name}.")
    except IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"Integrity Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing data: {str(e)}")





def import_csv_xlsx(file: UploadFile, db: Session, model) -> List[Any]:
    if file.content_type not in ["text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_content = io.BytesIO(file.file.read())
    df = pd.read_csv(file_content) if file.content_type == "text/csv" else pd.read_excel(file_content)

    # Validate and insert rows
    inserted_data = []
    for _, row in df.iterrows():
        obj_data = row.to_dict()
        db_obj = model(**obj_data)
        db.add(db_obj)
        inserted_data.append(db_obj)

    db.commit()
    return inserted_data


def import_sql(file: UploadFile, db: Session) -> None:
    if file.content_type != "application/sql":
        raise HTTPException(status_code=400, detail="Invalid SQL file format")
    
    sql_script = file.file.read().decode("utf-8")
    try:
        db.execute(sql_script)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
