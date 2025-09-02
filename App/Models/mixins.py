# models/mixins.py
from sqlalchemy import event
from Models.models import FileStorage

def _infer_file_type(file_url: str) -> str:
    """
    Infer file type based on file extension.
    """
    file_extension = file_url.split(".")[-1].lower()
    if file_extension in ["jpeg", "jpg", "png", "gif"]:
        return "Image"
    elif file_extension == "pdf":
        return "PDF"
    elif file_extension in ["doc", "docx"]:
        return "Document"
    else:
        return "File"

def register_file_path_listener(model, file_fields):
    """
    Register an event listener on the given model so that when a record is inserted or updated,
    file storage records are either created or updated automatically. Also, attach a deletion listener.
    
    - For each file field in `file_fields`:
      - If the field contains a dict (multiple files), iterate over its key/value pairs.
      - If it’s a string (single file), process it directly.
    - The listener uses the record’s ID and organization_id to check if a corresponding FileStorage record exists.
    - If an uploader’s ID is provided as a transient attribute (_uploaded_by_id), it will be set.
    """
    @event.listens_for(model, "after_insert")
    @event.listens_for(model, "after_update")
    def file_path_listener(mapper, connection, target):
        organization_id = getattr(target, "organization_id", None)
        uploader_id = getattr(target, "_uploaded_by_id", None)
        record_type = model.__tablename__
        
        for field in file_fields:
            value = getattr(target, field, None)
            if not value:
                continue
            # Process multiple file uploads (dict structure)
            if isinstance(value, dict):
                for file_name, file_url in value.items():
                    file_type = _infer_file_type(file_url)
                    existing = connection.execute(
                        FileStorage.__table__.select().where(
                            (FileStorage.record_id == target.id) &
                            (FileStorage.organization_id == organization_id) &
                            (FileStorage.record_type == record_type) &
                            (FileStorage.file_name == file_name)
                        )
                    ).fetchone()
                    if existing:
                        update_stmt = FileStorage.__table__.update().where(
                            FileStorage.__table__.c.id == existing.id
                        ).values(
                            file_path=file_url,
                            file_type=file_type,
                            uploaded_by_id=uploader_id
                        )
                        connection.execute(update_stmt)
                    else:
                        ins_stmt = FileStorage.__table__.insert().values(
                            file_name=file_name,
                            file_path=file_url,
                            file_type=file_type,
                            record_id=target.id,
                            record_type=record_type,
                            organization_id=organization_id,
                            uploaded_by_id=uploader_id
                        )
                        connection.execute(ins_stmt)
            # Process single file upload (string URL)
            elif isinstance(value, str):
                file_type = _infer_file_type(value)
                file_name = value.split("/")[-1]
                existing = connection.execute(
                    FileStorage.__table__.select().where(
                        (FileStorage.record_id == target.id) &
                        (FileStorage.organization_id == organization_id) &
                        (FileStorage.record_type == record_type) &
                        (FileStorage.file_name == file_name)
                    )
                ).fetchone()
                if existing:
                    update_stmt = FileStorage.__table__.update().where(
                        FileStorage.__table__.c.id == existing.id
                    ).values(
                        file_path=value,
                        file_type=file_type,
                        uploaded_by_id=uploader_id
                    )
                    connection.execute(update_stmt)
                else:
                    ins_stmt = FileStorage.__table__.insert().values(
                        file_name=file_name,
                        file_path=value,
                        file_type=file_type,
                        record_id=target.id,
                        record_type=record_type,
                        organization_id=organization_id,
                        uploaded_by_id=uploader_id
                    )
                    connection.execute(ins_stmt)

    @event.listens_for(model, "after_delete")
    def file_path_delete_listener(mapper, connection, target):
        """
        When a record is deleted, remove all associated FileStorage records.
        """
        organization_id = getattr(target, "organization_id", None)
        record_type = model.__tablename__
        delete_stmt = FileStorage.__table__.delete().where(
            (FileStorage.record_id == target.id) &
            (FileStorage.organization_id == organization_id) &
            (FileStorage.record_type == record_type)
        )
        connection.execute(delete_stmt)

    return file_path_listener


















# # models/mixins.py

# from sqlalchemy import event
# from Models.models import FileStorage  # assuming FileStorage is defined in Models/models.py

# def register_file_path_listener(model, file_fields):
#     """
#     Register an event listener that checks for file path URL fields and creates a FileStorage record.
#     :param model: SQLAlchemy model to attach listener to.
#     :param file_fields: List of field names on the model that store file path URLs.
#     """
#     @event.listens_for(model, "after_insert")
#     @event.listens_for(model, "after_update")
#     def file_path_listener(mapper, connection, target):
#         organization_id = getattr(target, "organization_id", None)
#         # For each declared file field on the model...
#         for field in file_fields:
#             value = getattr(target, field, None)
#             if value:
#                 # If the value is a list/JSON (e.g., for logos), iterate over it
#                 if isinstance(value, (list, tuple)):
#                     for file_url in value:
#                         _create_file_storage_record(connection, target.id, model.__tablename__, file_url, organization_id)
#                 else:
#                     _create_file_storage_record(connection, target.id, model.__tablename__, value, organization_id)
    
#     def _create_file_storage_record(connection, record_id, record_type, file_url, organization_id):
#         # Check if a FileStorage record already exists (implementation depends on your business rules)
#         ins_stmt = FileStorage.__table__.insert().values(
#             file_name=file_url.split("/")[-1],
#             file_path=file_url,
#             file_type="Document",  # or infer based on file extension
#             record_id=record_id,
#             record_type=record_type,
#             organization_id=organization_id,
#             uploaded_by_id=None  # Could be set if you have context for who uploaded it
#         )
#         connection.execute(ins_stmt)

#     return file_path_listener
