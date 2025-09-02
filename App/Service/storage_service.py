import os
import uuid
import logging
from io import BytesIO
from typing import List, Dict

from fastapi import HTTPException
from google.cloud import storage as gcs
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from Utils.file_handler import gcs_client

logger = logging.getLogger(__name__)

class BaseStorage:
    def upload(self, files: List[dict], folder: str) -> Dict[str, str]:
        raise NotImplementedError
    def download(self, path: str) -> bytes:
        raise NotImplementedError
    def delete(self, path: str) -> None:
        raise NotImplementedError
    def update(self, files: List[dict], folder: str) -> Dict[str, str]:
        """
        Default update = delete existing + upload new.
        Override if your backend supports true overwrite.
        """
        # by default we just call upload (most SDKs simply overwrite)
        return self.upload(files, folder)


class GoogleCloudStorage(BaseStorage):
    def __init__(self, bucket_name,):
        self.bucket_name = bucket_name
        # self.client = gcs_client
        self.bucket = gcs_client.bucket(bucket_name)

    def upload(self, files, folder):
        urls = {}
        for file in files:
            # Sanitize filename by replacing spaces with underscores
            original_filename = file['filename']
            sanitized_filename = original_filename.replace(' ', '_')
            
            blob_path = f"{folder}/{sanitized_filename}"
            blob = self.bucket.blob(blob_path)
            try:
                blob.upload_from_file(BytesIO(file['content']),
                                      content_type=file.get("content_type","application/octet-stream"))
                urls[original_filename] = f"https://storage.googleapis.com/{self.bucket_name}/{blob_path}"
            except Exception as e:
                logger.error(f"GCS upload error: {e}")
                raise
        return urls

    def download(self, path: str) -> bytes:
        blob = self.bucket.blob(path)
        try:
            return blob.download_as_bytes()
        except Exception as e:
            logger.error(f"GCS download error: {e}")
            raise HTTPException(status_code=404, detail="File not found in GCS")

    def delete(self, path: str) -> None:
        blob = self.bucket.blob(path)
        try:
            blob.delete()
        except Exception as e:
            logger.warning(f"GCS delete warning (might be already gone): {e}")

    # update() inherits default (just calls upload → overwrite)


class S3Storage(BaseStorage):
    def __init__(self, bucket_name, region, access_key, secret_key):
        self.bucket = bucket_name
        self.client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )

    def upload(self, files, folder):
        urls = {}
        for file in files:
            # Sanitize filename by replacing spaces with underscores
            original_filename = file['filename']
            sanitized_filename = original_filename.replace(' ', '_')
            
            key = f"{folder}/{sanitized_filename}"
            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=file['content'],
                    ContentType=file.get("content_type","application/octet-stream"),
                    ACL="public-read"
                )
                urls[original_filename] = f"https://{self.bucket}.s3.amazonaws.com/{key}"
            except (BotoCoreError, ClientError) as e:
                logger.error(f"S3 upload error: {e}")
                raise
        return urls

    def download(self, path: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=path)
            return resp['Body'].read()
        except self.client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="File not found in S3")
        except Exception as e:
            logger.error(f"S3 download error: {e}")
            raise

    def delete(self, path: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=path)
        except Exception as e:
            logger.warning(f"S3 delete warning: {e}")

    # update() inherits default


class LocalStorage(BaseStorage):
    def __init__(self, root: str, base_url:str):
        self.root = root
        # ensure no trailing slash
        self.base_url = base_url.rstrip("/")
        os.makedirs(self.root, exist_ok=True)

    def _full_path(self, path: str) -> str:
        # e.g. path = "org1/logos/foo.png"
        return os.path.join(self.root, path)

    def upload(self, files: List[dict], folder: str):
        urls = {}
        for file in files:
            rel_dir = folder
            target_dir = os.path.join(self.root, rel_dir)
            os.makedirs(target_dir, exist_ok=True)
            
            # Sanitize filename by replacing spaces with underscores
            original_filename = file["filename"]
            sanitized_filename = original_filename.replace(' ', '_')
            
            full_path = os.path.join(self.root, rel_dir, sanitized_filename)
            try:
                with open(full_path, "wb") as f:
                    f.write(file["content"])
                # You'd serve these under your `/static` mount:
                urls[original_filename] = f"{self.base_url}/static/{rel_dir}/{sanitized_filename}"
            except Exception as e:
                logger.error(f"Local FS upload error: {e}")
                raise
        return urls

    def download(self, path: str) -> bytes:
        full = self._full_path(path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found on disk")

    def delete(self, path: str) -> None:
        full = self._full_path(path)
        try:
            os.remove(full)
        except FileNotFoundError:
            logger.warning("Local FS delete warning: file already gone")
        except Exception as e:
            logger.error(f"Local FS delete error: {e}")

    def update(self, files, folder):
        # remove old then write new
        for file in files:
            rel_path = f"{folder}/{file['filename']}"
            try:
                self.delete(rel_path)
            except:
                pass
        return self.upload(files, folder)
