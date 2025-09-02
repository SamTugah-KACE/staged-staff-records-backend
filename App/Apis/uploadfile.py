from typing import List, Optional

# import urllib
import urllib.parse  # For decoding URL parameters
from Utils.storage_utils import get_storage_service
from Service.storage_service import BaseStorage
from Service.file_service import upload_file
from Utils.file_handler import get_gcs_client
from Utils.config import DevelopmentConfig
from fastapi import APIRouter, Depends, Form, Query, UploadFile, File, HTTPException, status
from google.cloud import storage
from Service.gcs_service import GoogleCloudStorage

# Create the FastAPI app
app = APIRouter()



@app.post("/GCS-File-Upload/",   status_code=status.HTTP_201_CREATED)
async def File_Upload(
   
    logos: Optional[List[UploadFile]] = File(None),  # Organization logos
    # user_images: Optional[List[UploadFile]] = File(None), 
storage: BaseStorage = Depends(get_storage_service),
):
    
    try:
        config = DevelopmentConfig()
        gcs_client = GoogleCloudStorage(bucket_name=config.BUCKET_NAME)

        if logos:
            logo_files = [{"filename": file.filename, "content": await file.read()} for file in logos]
          
            # logo_urls = gcs_client.upload_to_gcs(files=logo_files, folder=f"test2/v2") or {}

            logo_urls = storage.upload(files=logo_files, folder=f"test2/v2") or {}

        return logo_urls
    

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@app.get("/download_gcs_file/")
async def download_file(
   
    file_path: str = Query(..., description="Relative file path inside the GCS bucket"),
    render: bool = Query(False, description="Set to True to render image in FastAPI UI"),

):
    
    try:
        response = ''
        config = DevelopmentConfig()
        gcs_client = GoogleCloudStorage(bucket_name=config.BUCKET_NAME)
        # Decode URL-encoded file path
        decoded_file_path = urllib.parse.unquote(file_path)

        if file_path:
            response = gcs_client.download_from_gcs(file_path=decoded_file_path, show_image=render)
            print("response from download file operation: ", response)
        else:
           raise HTTPException(status_code=400, detail="File URL Required") 
        
        if response.status_code == 500  and   "File not found" in response.__str__:
            raise HTTPException(status_code=404, detail="File Not Found")
    
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.delete("/delete_gcs_file/")
async def delete_file(
   
    file_path: str = Query(..., description="Relative file path inside the GCS bucket"),
    

):
    
    try:
        response = ''
        config = DevelopmentConfig()
        gcs_client = GoogleCloudStorage(bucket_name=config.BUCKET_NAME)

         # Decode URL-encoded file path
        decoded_file_path = urllib.parse.unquote(file_path)

        if file_path:
            response = gcs_client.delete_from_gcs(file_path=decoded_file_path)
            print("response from delete file operation:: ", response)
        else:
           raise HTTPException(status_code=400, detail="File URL Required") 
    
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

