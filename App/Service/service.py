from google.cloud import storage  # For Google Cloud Storage integration
import os

def upload_to_google_cloud(file_data: bytes, file_name: str, bucket_name: str) -> str:
    """
    Upload a file to Google Cloud Storage and return the public URL.

    :param file_data: File data as bytes
    :param file_name: File name to save in the bucket
    :param bucket_name: Google Cloud Storage bucket name
    :return: Public URL of the uploaded file
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    blob.upload_from_string(file_data)
    blob.make_public()
    return blob.public_url