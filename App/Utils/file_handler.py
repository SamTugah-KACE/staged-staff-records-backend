import aiofiles
from fastapi import UploadFile, HTTPException
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from google.cloud import storage
from Utils.config import DevelopmentConfig, get_config
import os
from io import BytesIO
from fastapi.responses import FileResponse
import shutil
import logging
from google.cloud import storage
import json


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# settings = DevelopmentConfig()
settings = get_config()

# Helper function to validate file extensions
def validate_file_type(file: UploadFile, allowed_extensions: list):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is empty")
    
    extension = file.filename.rsplit(".", 1)[-1].lower()  # Use rsplit to avoid issues with multiple dots
    if extension not in allowed_extensions:
        logger.error(f"File type '{extension}' is not allowed")
        raise HTTPException(status_code=400, detail="File type not allowed")


async def validate_file(file: UploadFile, allowed_extensions: list, max_file_size: int =None):
    validate_file_type(file, allowed_extensions)
    if max_file_size:
        content = await file.read()
        if len(content) > max_file_size:
            logger.error("File exceeds the maximum allowed size.")
            raise HTTPException(status_code=413, detail="File too large")




# Local Storage (via aiofiles)
async def save_file_to_local(file: UploadFile, path: str, max_file_size: int = 10 * 1024 * 1024):  # 10 MB limit
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

    filepath = os.path.join(path, file.filename)

    content = await file.read()
    if len(content) > max_file_size:
        logger.error("File exceeds the maximum allowed size.")
        raise HTTPException(status_code=413, detail="File too large")

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    logger.info(f"File saved to local storage at {filepath}")
    return filepath



async def read_file_from_local(file_path: str):
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


async def delete_file_from_local(file_path: str):
    if os.path.exists(file_path):
        os.remove(file_path)
        logger.info(f"File deleted from local storage: {file_path}")
    else:
        logger.error(f"File not found: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")



# # Amazon S3 (via boto3)
# s3_client = boto3.client("s3")

# def upload_file_to_s3(file: UploadFile, bucket: str = settings.S3_BUCKET_NAME):
#     try:
#         s3_client.upload_fileobj(file.file, bucket, file.filename)
#         file_url = f"s3://{bucket}/{file.filename}"
#         logger.info(f"File uploaded to S3 at {file_url}")
#         return file_url
#     except NoCredentialsError:
#         logger.error("S3 credentials not found.")
#         raise HTTPException(status_code=400, detail="S3 credentials not found")
#     except ClientError as e:
#         logger.error(f"Error uploading file to S3: {str(e)}")
#         raise HTTPException(status_code=500, detail="Error uploading file to S3")


# def read_file_from_s3(file_key: str, bucket: str = settings.S3_BUCKET_NAME):
#     try:
#         file_obj = s3_client.get_object(Bucket=bucket, Key=file_key)
#         file_stream = file_obj["Body"].read()
#         logger.info(f"File retrieved from S3: {file_key}")
#         return BytesIO(file_stream)
#     except ClientError as e:
#         logger.error(f"File not found in S3: {file_key}")
#         raise HTTPException(status_code=404, detail=f"File not found in S3: {str(e)}")


# def download_file_from_s3(file_key: str, bucket: str = settings.S3_BUCKET_NAME):
#     try:
#         file_obj = s3_client.get_object(Bucket=bucket, Key=file_key)
#         file_stream = file_obj["Body"].read()
#         logger.info(f"File retrieved from S3: {file_key}")
#         return BytesIO(file_stream)
#     except ClientError as e:
#         logger.error(f"Error downloading file from S3: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Error downloading file from S3: {str(e)}")


# def delete_file_from_s3(file_key: str, bucket: str = settings.S3_BUCKET_NAME):
#     try:
#         s3_client.delete_object(Bucket=bucket, Key=file_key)
#         logger.info(f"File deleted from S3: {file_key}")
#     except ClientError as e:
#         logger.error(f"Error deleting file from S3: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Error deleting file from S3: {str(e)}")



# Load GCS credentials from the provided json file
# def get_gcs_client():

#     # Get the path to the Google Cloud API JSON file from an environment variable
#     gcloud_credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
#     print("path: ", gcloud_credentials_path)
#     print(os.path.exists(gcloud_credentials_path))
#     if os.path.exists(gcloud_credentials_path):
#        with open(gcloud_credentials_path) as f:
#             credentials_info = json.load(f)
       
#     else:
#         print("else")
#         credentials_info = settings.GCS_CREDENTIALS
#         if not credentials_info or "private_key" not in credentials_info:
#             raise ValueError("Invalid or missing GCS credentials.")

#     # print("credential_info: ", credentials_info)
        
    
#     return storage.Client.from_service_account_info(credentials_info)

# client = get_gcs_client()

# def get_gcs_client():
#     # Get the path to the Google Cloud API JSON file from an environment variable
#     # Check if the GOOGLE_APPLICATION_CREDENTIALS file exists.
#     gcloud_credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS if hasattr(settings, "GOOGLE_APPLICATION_CREDENTIALS") else None
    
#     # print("path: ", gcloud_credentials_path)
#     # print(os.path.exists(gcloud_credentials_path))
    
#     if gcloud_credentials_path and os.path.exists(gcloud_credentials_path):
#         with open(gcloud_credentials_path) as f:
#             credentials_info = json.load(f)
#     else:
#         credentials_info = settings.GCS_CREDENTIALS
#         if not credentials_info or "private_key" not in credentials_info:
#             raise ValueError("Invalid or missing GCS credentials.")

#     return storage.Client.from_service_account_info(
#         credentials_info,
#         project=credentials_info.get("project_id")
#     )

# client = get_gcs_client()


def get_gcs_client():
    """
    Return a GCS client or None on any connection error.
    """
    try:
        creds = settings.GCS_CREDENTIALS
        client = storage.Client.from_service_account_info(
            creds, project=creds.get("project_id")
        )
        # quick check
        _ = list(client.list_buckets(page_size=1))

        print("client from file_handler:: ", client)
        return client
    except Exception as e:
        logger.warning(f"GCS init failed, skipping GCS usage: {e}")
        return None

class GCSClientWrapper:
    _client = None

    @classmethod
    def client(cls):
        if cls._client is None:
            cls._client = get_gcs_client()
        return cls._client

gcs_client = GCSClientWrapper.client()


def upload_file_to_gcs(file: UploadFile, folder:str, bucket_name=settings.BUCKET_NAME):
    
    if not file.filename or "." not in file.filename:
        logger.error(f"Invalid filename: {file.filename}")
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = file.filename.rsplit(".", 1)[-1].lower()  # Use rsplit to avoid issues with multiple dots
    storage_path = f'developers-bucket/test-app/{folder}'
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(storage_path)
  
    try:
        blob.upload_from_file(file.file)
       
        path = f'https://storage.googleapis.com/{bucket_name}/{storage_path}'
        print("path: ", path)
        return path
    except Exception as e:
        logger.error(f"Error uploading file to GCS: {str(e)}")
        print(f"Error uploading file to GCS: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading file to GCS: {str(e)}")




def read_file_from_gcs(file_name: str, bucket_name=settings.BUCKET_NAME):
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        if not blob.exists():
            raise HTTPException(status_code=404, detail="File not found in GCS")
        file_content = blob.download_as_bytes()
        return BytesIO(file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file from GCS: {str(e)}")

def download_file_from_gcs(file_name: str, bucket_name=settings.BUCKET_NAME):
    file_stream = read_file_from_gcs(file_name, bucket_name)
    return file_stream

def delete_file_from_gcs(file_name: str, bucket_name=settings.BUCKET_NAME):
    try:
        bucket = client.bucket(bucket_name)
        ext = file_name.rsplit(".", 1)[-1].lower()  # Use rsplit to avoid issues with multiple dots
        print("ext: ", ext)
        storage_path = ''
        if ext in ['png', 'jpg', 'jpeg']:
            storage_path = 'developers-bucket/test-app/file_path/media/images/'+file_name
        elif ext in ['docx', 'pdf', 'txt']:
            storage_path = bucket_name+'/test-app/file_path/docs/'+file_name
        # blob = bucket.blob(file_name)
        blob = bucket.blob(storage_path)
        blob.delete() 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file from GCS: {str(e)}")




