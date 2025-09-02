from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from Utils.file_handler import (
    validate_file_type, save_file_to_local, read_file_from_local, 
    delete_file_from_local,
    upload_file_to_gcs, read_file_from_gcs, download_file_from_gcs, delete_file_from_gcs
)
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

# Allowed extensions to ensure secure file uploads
ALLOWED_EXTENSIONS = ['png', 'jpg', 'jpeg', 'pdf', 'docx', 'txt']


def upload_file(file: UploadFile, storage_option: str, folder: str):
    validate_file_type(file, ALLOWED_EXTENSIONS)  # Validate file type

    if storage_option.lower() == "local":
        return save_file_to_local(file, "local/storage")
    # elif storage_option.lower() == "s3":
    #     return upload_file_to_s3(file)
    elif storage_option.lower() == "gcs":
        return upload_file_to_gcs(file, folder)
    else:
        raise ValueError("Invalid storage option")

async def read_file(file_name: str, storage_option: str):
    if storage_option.lower() == "local":
        return FileResponse(path=f"local/storage/{file_name}", filename=file_name)
    # elif storage_option.lower() == "s3":
    #     file_stream = read_file_from_s3(file_name)
        # return StreamingResponse(BytesIO(file_stream), media_type="application/octet-stream")
    elif storage_option.lower() == "gcs":
        file_stream = read_file_from_gcs(file_name)
        return StreamingResponse(BytesIO(file_stream), media_type="application/octet-stream")
    else:
        raise HTTPException(status_code=400, detail="Invalid storage option")

async def download_file(file_name: str, storage_option: str):
    if storage_option.lower() == "local":
        return FileResponse(path=f"local/storage/{file_name}", filename=file_name)
    # elif storage_option.lower() == "s3":
    #     file_stream = download_file_from_s3(file_name)
    #     return StreamingResponse(BytesIO(file_stream), media_type="application/octet-stream",
    #                              headers={"Content-Disposition": f"attachment; filename={file_name}"})
    elif storage_option.lower() == "gcs":
        file_stream = download_file_from_gcs(file_name)
        return StreamingResponse(BytesIO(file_stream), media_type="application/octet-stream",
                                 headers={"Content-Disposition": f"attachment; filename={file_name}"})
    else:
        raise HTTPException(status_code=400, detail="Invalid storage option")

async def delete_file(file_name: str, storage_option: str):
    if storage_option.lower() == "local":
        return await delete_file_from_local(f"local/storage/{file_name}")
    # elif storage_option.lower() == "s3":
    #     return delete_file_from_s3(file_name)
    elif storage_option.lower() == "gcs":
        return delete_file_from_gcs(file_name)
    else:
        raise HTTPException(status_code=400, detail="Invalid storage option")



