from fastapi import Depends, HTTPException
from Service.storage_service import (
    GoogleCloudStorage, S3Storage, LocalStorage, BaseStorage
)
from .config import ProductionConfig, get_config
import logging

logger = logging.getLogger(__name__)


# def get_storage_service(
#     config: DevelopmentConfig = Depends(get_config),
# ) -> BaseStorage:
#     gcs = GoogleCloudStorage(config.BUCKET_NAME)
#     s3  = S3Storage(
#         bucket_name=config.AWS_S3_BUCKET,
#         region=config.AWS_REGION,
#         access_key=config.AWS_ACCESS_KEY,
#         secret_key=config.AWS_SECRET_KEY,
#     )
#     local = LocalStorage(root=config.STORAGE_ROOT)

def get_storage_service(
    config: ProductionConfig = Depends(get_config),
) -> BaseStorage:
    backends = []

    # GCS
    if getattr(config, "GCS_BUCKET", None):
        try:
            print("\n\nGCS BUCKET NAME:: ", config.BUCKET_NAME)
            backends.append(GoogleCloudStorage(config.BUCKET_NAME))
            print("backend in get_storage_service:: ", backends[0])
        except Exception as e:
            logger.warning(f"\n\n\n\nGCS init failed: {e}")

    # S3
    if all([
        getattr(config, "AWS_S3_BUCKET", None),
        getattr(config, "AWS_ACCESS_KEY", None),
        getattr(config, "AWS_SECRET_KEY", None),
        getattr(config, "AWS_REGION", None),
    ]):
        try:
            backends.append(
                S3Storage(
                    config.AWS_S3_BUCKET,
                    config.AWS_REGION,
                    config.AWS_ACCESS_KEY,
                    config.AWS_SECRET_KEY,
                )
            )
        except Exception as e:
            logger.warning(f"S3 init failed: {e}")

    # Local
    if getattr(config, "STORAGE_ROOT", None):
        try:
            backends.append(LocalStorage(config.STORAGE_ROOT, config.API_BASE_URL))
        except Exception as e:
            logger.warning(f"Local init failed: {e}")

    if not backends:
        raise HTTPException(500, "No valid storage backend configured.")



    class FallbackStorage(BaseStorage):
        def __init__(self, backends):
            self.backends = backends

        def upload(self, files, folder):
            for b in self.backends:
                try:
                    print(f"b in FallbackStorage:: {b} .upload {b.upload(files, folder)}")
                    return b.upload(files, folder)
                except Exception as e:
                    logger.warning(f"\n\n{b.__class__.__name__} upload failed: {e}")
            raise HTTPException(status_code=500, detail="All storage backends failed to upload.")

        def download(self, path: str) -> bytes:
            for b in self.backends:
                try:
                    return b.download(path)
                except HTTPException as he:
                    # 404 means “not here”—try next
                    if he.status_code == 404:
                        continue
                    raise
                except Exception:
                    continue
            raise HTTPException(status_code=404, detail="File not found in any storage backend.")

        def delete(self, path: str) -> None:
            for b in self.backends:
                try:
                    b.delete(path)
                    return
                except Exception:
                    continue
            # If none succeeded, we log but don’t necessarily error:
            logger.error("All storage backends failed to delete.")

        def update(self, files, folder):
            # by default, overwrite in whichever first works
            for b in self.backends:
                try:
                    return b.update(files, folder)
                except Exception as e:
                    logger.warning(f"{b.__class__.__name__} update failed: {e}")
            raise HTTPException(status_code=500, detail="All storage backends failed to update.")

    return FallbackStorage(backends)
