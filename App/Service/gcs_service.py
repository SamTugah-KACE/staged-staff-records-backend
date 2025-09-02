import base64
from io import BytesIO
import mimetypes
import re
from fastapi.responses import FileResponse
from google.cloud import storage
import uuid
from typing import Optional, List, Dict, Union
import logging
from fastapi import HTTPException
from Utils.file_handler import get_gcs_client, gcs_client
from google.cloud.storage.blob import Blob
from Utils.config import DevelopmentConfig, get_config
import os
import tempfile
import urllib.parse




# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


settings = get_config()

class GoogleCloudStorage:
    def __init__(self, bucket_name: str):
        # self.client = storage.Client()
        self.client = gcs_client
        self.bucket_name = bucket_name
        self.bucket = self.client.get_bucket(bucket_name) if self.client else None
        self.public_urls = {}
    

    def generate_signed_url(self, blob: Blob, expiration: int = 3600) -> str:
        """
        Generate a signed URL for accessing the uploaded file.
        ==========================================================
        :param blob: Blob object of the uploaded file
        :param expiration: Expiration time in seconds (default is 1 hour)
        :return: Signed URL for the blob
        """
        return blob.generate_signed_url(expiration=expiration)
    
    
    def extract_gcs_file_path(self, file_path: str) -> str:
        """
        Detects if the provided file path is a full GCS URL or a relative path.
        Converts it to the correct GCS file path for use in GCS API operations.

        :param file_path: Full GCS URL or relative file path.
        :return: Extracted relative GCS file path (inside the bucket).
        """
        try:
            # Decode URL-encoded file paths
            decoded_path = urllib.parse.unquote(file_path)

            # Regex pattern to detect a full GCS URL
            gcs_url_pattern = re.compile(r"https://storage\.googleapis\.com/([^/]+)/(.+)")
            
            match = gcs_url_pattern.match(decoded_path)
            if match:
                bucket_name, extracted_path = match.groups()

                # Ensure the bucket name matches before allowing conversion
                if bucket_name != settings.BUCKET_NAME:
                    raise ValueError(f"Provided URL is not from the expected bucket: {settings.BUCKET_NAME}")

                print("\n\nExtracted path: ", extracted_path)
                return extracted_path  # Return the correct file path inside the GCS bucket

            print("\n\nDecoded path: ", decoded_path)
            # If the path is already relative (not a full URL), return it as is
            return decoded_path
        except Exception as e:
            print("file path extraction error: ", e)
    


    def upload_to_gcs(self, files: List[dict], folder: str) -> Dict[str, str]:
        """
        Uploads files to Google Cloud Storage and returns their public URLs.
        
        :param bucket_name: Name of the GCS bucket.
        :param files: List of file objects containing `filename` and `content` (binary data).
        :param folder: Target folder in the bucket.
        :return: Dictionary of original filenames and their respective public URLs.
        """
        
        self.public_urls = {}

        for file in files:
            # Sanitize filename by replacing spaces with underscores
            original_filename = file["filename"]
            sanitized_filename = original_filename.replace(' ', '_')
            
            storage_path = f'test-app/{folder}/{sanitized_filename}'
            blob = self.bucket.blob(storage_path)
            
            try: 
                # Convert file content to a BytesIO object
                file_content = BytesIO(file['content'])
                blob.upload_from_file(file_content, content_type="image/*")

                print("\nblob: ", blob)
                print("\n\nstorage_path: ", storage_path)
               
                
                self.public_urls[original_filename] = f'https://storage.googleapis.com/{settings.BUCKET_NAME}/{storage_path}'
              
            except Exception as e:
                logger.error(f"\n\nError uploading file to GCS: {str(e)}")
                print(f"\n\nError uploading file to GCS: {str(e)}")
                # raise HTTPException(status_code=500, detail=f"\nError uploading file to GCS: {str(e)}")
                continue

            if self.public_urls == {}:
                self.public_urls = ""
        
        print("\n\npublic_urls:: ", self.public_urls)
        
        return self.public_urls
    

    def save_temp_file(self, file_stream: BytesIO, file_name: str) -> str:
        """
        Saves the file temporarily in the system for further processing.
        
        :param file_stream: File content in a BytesIO stream.
        :param file_name: Name of the file including extension.
        :return: Path to the saved temporary file.
        """
        try:
            temp_dir = tempfile.mkdtemp()  # Create a temp directory
            file_path = os.path.join(temp_dir, file_name)

            with open(file_path, "wb") as temp_file:
                temp_file.write(file_stream.getbuffer())

            logger.info(f"File temporarily saved at: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error saving temporary file: {str(e)}")
            raise HTTPException(status_code=500, detail="Error saving temporary file")


    def download_from_gcs(self, file_path: str, show_image: bool) -> Union[FileResponse, str]:
        """
            Downloads a file from Google Cloud Storage and returns it in a format suitable
            for frontend consumption.

            If show_image is True and the file is an image, the function returns a base64
            encoded data URL (e.g., "data:image/jpeg;base64,...") for inline rendering.
            Otherwise, it returns a FileResponse as an attachment for download.

            :param file_path: The file path in the GCS bucket (e.g., 'test-app/organizations/.../image.jpg').
            :param show_image: Boolean flag indicating if the image should be rendered inline.
            :return: A base64 data URL (if inline) or a FileResponse for download.
        """
        try:
            path = self.extract_gcs_file_path(file_path=file_path)
            print("\n\nDecoded file path for retrieval: ", path)
            try:
                blob = self.bucket.blob(path)
            except Exception as ee:
                print("blob error: ", ee)
            
            
            if not blob.exists():
                logger.error(f"File not found in GCS: {path}")
                raise FileNotFoundError(f"File not found in GCS: {path}")

            file_stream = BytesIO()
            blob.download_to_file(file_stream)
            file_stream.seek(0)  # Reset stream position to the beginning

            logger.info(f"file content: {file_stream}")
            logger.info(f"Successfully downloaded file from GCS: {path}")

            # Determine file name and content type
            filename = os.path.basename(path)
            content_type, _ = mimetypes.guess_type(filename)
            if content_type is None:
                content_type = "application/octet-stream"  # Default for unknown files
            
           

            # Save file temporarily for further processing
            temp_file_path = self.save_temp_file(file_stream, filename)

            logger.info(f"Successfully downloaded and saved: {temp_file_path}")

            # If it's an image and `show_image=True`, render it in Swagger UI
            if show_image and content_type.startswith("image"):
                # Reset stream position (if necessary) to encode the file content.
                file_stream.seek(0)
                try:
                    encoded_image = base64.b64encode(file_stream.getvalue()).decode("utf-8")
                except Exception as e:
                    print("error encoding image to base64: ", e)
            
                    return ""
                # Return as a data URL (suitable for inline rendering in HTML).
                return f"data:{content_type};base64,{encoded_image}"  # Base64 format for inline rendering
                # return FileResponse(temp_file_path, media_type=content_type)

            # Otherwise, return file as an attachment for download
            return FileResponse(temp_file_path, media_type=content_type, filename=filename)
            # return file_stream
            # return base64.b64encode(file_stream).decode("utf-8")
        
        except Exception as e:
            logger.error(f"Error downloading file from GCS: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    

    
    

    def delete_from_gcs(self, file_path: str) -> bool:
        """
        Deletes a file from Google Cloud Storage.
        
        :param file_path: Path of the file in the GCS bucket (e.g., 'test-app/organizations/.../image.jpg').
        :return: True if deleted successfully, False otherwise.
        """
        try:
            path = self.extract_gcs_file_path(file_path)
            print("\n\nDecoded file path for deletion: ", path)
            blob = self.bucket.blob(path)
            if not blob.exists():
                logger.warning(f"File not found, cannot delete: {path}")
                return False  # File does not exist
            
            blob.delete()
            logger.info(f"Successfully deleted file from GCS: {path}")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting file from GCS: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error deleting file from GCS: {str(e)}")
     


    def upload_file(self, file_data: bytes, file_name: str) -> str:
        """
        Uploads a file to GCS and returns the file's public URL.

        :param file_data: File content in bytes
        :param file_name: Desired file name (e.g., 'logos/my_logo.png')
        :return: Public URL of the uploaded file
        """
        try:
            blob = self.bucket.blob(file_name)
            blob.upload_from_string(file_data)
            blob.make_public()
            return blob.public_url
        except Exception as e:
            raise Exception(f"Failed to upload file to GCS: {str(e)}")

    def delete_file(self, file_name: str) -> bool:
        """
        Deletes a file from GCS.

        :param file_name: Name of the file in the bucket
        :return: True if deletion is successful, False otherwise
        """
        try:
            blob = self.bucket.blob(file_name)
            blob.delete()
            return True
        except Exception as e:
            raise Exception(f"Failed to delete file from GCS: {str(e)}")
