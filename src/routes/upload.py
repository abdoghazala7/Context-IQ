from fastapi import FastAPI, APIRouter, Depends, File, UploadFile, status
from controllers import uploadcontroller 
from fastapi.responses import JSONResponse
from helpers.config import Config , get_config
from models import responsesignal
import aiofiles
import logging


logger = logging.getLogger('uvicorn.error')

Upload_router = APIRouter(
    prefix="/api/v1",  
    tags=["File Upload"]
)

@Upload_router.post("/upload/{project_id}")
async def upload_file(
    project_id : str,
    file: UploadFile = File(...),
    config: Config = Depends(get_config)
):
    """
    Endpoint to upload a file for a specific project.
    """

    upload_controller = uploadcontroller()

    is_valid, message = upload_controller.validate_uploaded_file(file=file)
    if not is_valid:
        logger.error(f"File validation failed: {message}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": message}
        )
    
    file_path, file_id = upload_controller.generate_unique_filepath(
        orig_file_name=file.filename,
        project_id=project_id
    )

    try:
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(config.FILE_DEFAULT_CHUNK_SIZE):
                await f.write(chunk)
    except Exception as e:

        logger.error(f"Error while uploading file: {e}")

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": responsesignal.FILE_UPLOAD_FAILED.value
            }
        )
    
    logger.info(responsesignal.FILE_UPLOAD_SUCCESS.value)
    
    return JSONResponse(
            content={
                "signal": responsesignal.FILE_UPLOAD_SUCCESS.value,
                "file_id": file_id
            }
        )
    
    
