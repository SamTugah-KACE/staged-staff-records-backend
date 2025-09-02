import aiofiles
from fastapi import UploadFile, HTTPException
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from google.cloud import storage
from core.config import settings
import os
from io import BytesIO
from fastapi.responses import FileResponse
import shutil
import logging
import json


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Helper function to validate file extensions
def validate_file_type(file: UploadFile, allowed_extensions: list):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is empty")
    
    extension = file.filename.rsplit(".", 1)[-1].lower()  # Use rsplit to avoid issues with multiple dots
    if extension not in allowed_extensions:
        logger.error(f"File type '{extension}' is not allowed")
        raise HTTPException(status_code=400, detail="File type not allowed")


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



# Amazon S3 (via boto3)
s3_client = boto3.client("s3")

def upload_file_to_s3(file: UploadFile, bucket: str = settings.S3_BUCKET_NAME):
    try:
        s3_client.upload_fileobj(file.file, bucket, file.filename)
        file_url = f"s3://{bucket}/{file.filename}"
        logger.info(f"File uploaded to S3 at {file_url}")
        return file_url
    except NoCredentialsError:
        logger.error("S3 credentials not found.")
        raise HTTPException(status_code=400, detail="S3 credentials not found")
    except ClientError as e:
        logger.error(f"Error uploading file to S3: {str(e)}")
        raise HTTPException(status_code=500, detail="Error uploading file to S3")


def read_file_from_s3(file_key: str, bucket: str = settings.S3_BUCKET_NAME):
    try:
        file_obj = s3_client.get_object(Bucket=bucket, Key=file_key)
        file_stream = file_obj["Body"].read()
        logger.info(f"File retrieved from S3: {file_key}")
        return BytesIO(file_stream)
    except ClientError as e:
        logger.error(f"File not found in S3: {file_key}")
        raise HTTPException(status_code=404, detail=f"File not found in S3: {str(e)}")


def download_file_from_s3(file_key: str, bucket: str = settings.S3_BUCKET_NAME):
    try:
        file_obj = s3_client.get_object(Bucket=bucket, Key=file_key)
        file_stream = file_obj["Body"].read()
        logger.info(f"File retrieved from S3: {file_key}")
        return BytesIO(file_stream)
    except ClientError as e:
        logger.error(f"Error downloading file from S3: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading file from S3: {str(e)}")


def delete_file_from_s3(file_key: str, bucket: str = settings.S3_BUCKET_NAME):
    try:
        s3_client.delete_object(Bucket=bucket, Key=file_key)
        logger.info(f"File deleted from S3: {file_key}")
    except ClientError as e:
        logger.error(f"Error deleting file from S3: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting file from S3: {str(e)}")



# Load GCS credentials from the provided json file
def get_gcs_client():

    # Get the path to the Google Cloud API JSON file from an environment variable
    gcloud_credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    print("file exists: ", os.path.exists(gcloud_credentials_path))
    with open(gcloud_credentials_path) as f:
    # with open('./google_cloud_storage_api.json') as f:
        # print("load file: ",json.load(f))
        credentials_info = json.load(f)
        print("\ncredential info: ", credentials_info)
    return storage.Client.from_service_account_info(credentials_info)

client = get_gcs_client()



def upload_file_to_gcs(file: UploadFile, bucket_name=settings.GCS_BUCKET_NAME):
    print("bucket_name: ", bucket_name)
    if not file.filename or "." not in file.filename:
        logger.error(f"Invalid filename: {file.filename}")
        print(f"Invalid filename: {file.filename}")
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = file.filename.rsplit(".", 1)[-1].lower()  # Use rsplit to avoid issues with multiple dots
    print("ext: ", ext)
    storage_path = ''
    if ext in ['png', 'jpg', 'jpeg']:
        storage_path = 'developers-bucket/test-app/file_path/media/images/'+file.filename
    elif ext in ['docx', 'pdf', 'txt']:
        storage_path = bucket_name+'/test-app/file_path/docs/'+file.filename
    bucket = client.bucket(bucket_name)
    print("bucket: ", bucket)
    # bucket = client.bucket(storage_path)
    # blob = bucket.blob(file.filename)
    blob = bucket.blob(storage_path)
    print("blob: ", blob)
    try:
        blob.upload_from_file(file.file)
        print("storage_path: ", storage_path)
        path = f'https://storage.googleapis.com/{bucket_name}/{storage_path}'
        print("path: ", path)
        return path
        # return f'https://storage.googleapis.com/{storage_path}/{file.filename}'
        # return f"gs://{bucket_name}/{path}/{file.filename}"
        # return f"gs://{bucket_name}/{file.filename}"
    except Exception as e:
        logger.error(f"Error uploading file to GCS: {str(e)}")
        print(f"Error uploading file to GCS: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading file to GCS: {str(e)}")




def read_file_from_gcs(file_name: str, bucket_name=settings.GCS_BUCKET_NAME):
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        if not blob.exists():
            raise HTTPException(status_code=404, detail="File not found in GCS")
        file_content = blob.download_as_bytes()
        return BytesIO(file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file from GCS: {str(e)}")

def download_file_from_gcs(file_name: str, bucket_name=settings.GCS_BUCKET_NAME):
    file_stream = read_file_from_gcs(file_name, bucket_name)
    return file_stream

def delete_file_from_gcs(file_name: str, bucket_name=settings.GCS_BUCKET_NAME):
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




# GCS Operations
# def upload_file_to_gcs(file: UploadFile, bucket_name=settings.GCS_BUCKET_NAME):
#     bucket = client.bucket(bucket_name)
#     blob = bucket.blob(file.filename)
#     blob.upload_from_file(file.file)
#     return f"gs://{bucket_name}/{file.filename}"

# def upload_file_to_gcs(file: UploadFile, bucket_name=settings.GCS_BUCKET_NAME):
#     if not file.filename:
#         raise HTTPException(status_code=400, detail="Filename is empty")

#     bucket = client.bucket(bucket_name)
#     blob = bucket.blob(file.filename)
#     try:
#         blob.upload_from_file(file.file)
#         return f"gs://{bucket_name}/{file.filename}"
#     except Exception as e:
#         logger.error(f"Error uploading file to GCS: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Error uploading file to GCS: {str(e)}")

# import aiofiles
# from fastapi import UploadFile, HTTPException
# import boto3
# from botocore.exceptions import NoCredentialsError, ClientError
# from core.config import settings
# from google.cloud import storage
# import os
# from io import BytesIO
# from fastapi.responses import FileResponse
# import shutil


# # Helper function to validate file extensions
# def validate_file_type(file: UploadFile, allowed_extensions: list):
#     extension = file.filename.split(".")[-1]
#     if extension not in allowed_extensions:
#         raise HTTPException(status_code=400, detail="File type not allowed")
    


# #Local Storage (via aiofiles)
# async def save_file_to_local(file: UploadFile, path: str):

#     # Ensure the upload directory exists
#     if not os.path.exists(path):
#         os.makedirs(path, exist_ok=True)
    
#     filepath = os.path.join(path, file.filename)

#     # Save the original image file
#     # with open(filepath, 'wb') as buffer:
#     #     shutil.copyfileobj(file.file, buffer)

#     # return filepath
        
#     async with aiofiles.open(f"{path}/{file.filename}", "wb") as f:
#         content = await file.read()
#         await f.write(content)
#     return f"{path}/{file.filename}"

    




# # Local Storage (via aiofiles)
# async def read_file_from_local(file_path: str):
#     if not os.path.exists(file_path):
#         raise HTTPException(status_code=404, detail="File not found")
#     print("file_path: ", file_path)
#     return FileResponse(file_path)  # FastAPI helper to send files



# async def download_file_from_local(file_path: str):
#     # return await read_file_from_local(file_path)
#     if not os.path.exists(file_path):
#         raise HTTPException(status_code=404, detail="File not found")
#     print("file_path: ", file_path)
#     return FileResponse(file_path)  # FastAPI helper to send files



# async def delete_file_from_local(file_path: str):
#     if os.path.exists(file_path):
#         os.remove(file_path)
#     else:
#         raise HTTPException(status_code=404, detail="File not found")
    





# #Amazon S3 (via boto3)
# s3_client = boto3.client("s3")

# def upload_file_to_s3(file, bucket=settings.S3_BUCKET_NAME):
#     try:
#         s3_client.upload_fileobj(file.file, bucket, file.filename)
#         return f"s3://{bucket}/{file.filename}"
#     except NoCredentialsError:
#         raise HTTPException(status_code=400, detail="S3 credentials not found")

# def read_file_from_s3(file_key: str, bucket=settings.S3_BUCKET_NAME):
#     try:
#         file_obj = s3_client.get_object(Bucket=bucket, Key=file_key)
#         file_stream = file_obj["Body"].read()
#         return BytesIO(file_stream)  # Stream as BytesIO object for download
#     except ClientError as e:
#         raise HTTPException(status_code=404, detail=f"File not found in S3: {str(e)}")


# def download_file_from_s3(file_key: str, bucket=settings.S3_BUCKET_NAME):
#     file_stream = read_file_from_s3(file_key, bucket)
#     return file_stream

# def delete_file_from_s3(file_key: str, bucket=settings.S3_BUCKET_NAME):
#     try:
#         s3_client.delete_object(Bucket=bucket, Key=file_key)
#     except ClientError as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting file from S3: {str(e)}")



# # #Google Cloud Storage (via google-cloud-storage)
# # client = storage.Client()

# # def upload_file_to_gcs(file, bucket_name=settings.GCS_BUCKET_NAME):
# #     bucket = client.bucket(bucket_name)
# #     blob = bucket.blob(file.filename)
# #     blob.upload_from_file(file.file)
# #     return f"gs://{bucket_name}/{file.filename}"

# # def read_file_from_gcs(file_name: str, bucket_name=settings.GCS_BUCKET_NAME):
# #     try:
# #         bucket = client.bucket(bucket_name)
# #         blob = bucket.blob(file_name)
        
# #         if not blob.exists():
# #             raise HTTPException(status_code=404, detail="File not found in GCS")
        
# #         file_content = blob.download_as_bytes()
# #         return BytesIO(file_content)
# #     except Exception as e:
# #         raise HTTPException(status_code=500, detail=f"Error reading file from GCS: {str(e)}")


# # def download_file_from_gcs(file_name: str, bucket_name=settings.GCS_BUCKET_NAME):
# #     file_stream = read_file_from_gcs(file_name, bucket_name)
# #     return file_stream


# # def delete_file_from_gcs(file_name: str, bucket_name=settings.GCS_BUCKET_NAME):
# #     try:
# #         bucket = client.bucket(bucket_name)
# #         blob = bucket.blob(file_name)
# #         blob.delete()
# #     except Exception as e:
# #         raise HTTPException(status_code=500, detail=f"Error deleting file from GCS: {str(e)}")
