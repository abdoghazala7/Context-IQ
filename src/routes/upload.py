from fastapi import FastAPI, APIRouter, Depends, File, UploadFile, status
from controllers import uploadcontroller, processcontroller
from fastapi.responses import JSONResponse
from helpers.config import Config , get_config
from models import responsesignal
from routes.schemes import processrequest
import aiofiles
import logging


logger = logging.getLogger('uvicorn.error')

Data_router = APIRouter(
    prefix="/api/v1",  
    tags=["File Upload"]
)

@Data_router.post("/upload/{project_id}")
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



@Data_router.post("/process/{project_id}")
async def process_file(
    project_id: str,
    process_request: processrequest
):

    file_id = process_request.file_id
    chunk_size = process_request.chunk_size
    overlap_size = process_request.overlap_size

    process_ctrl = processcontroller(project_id=project_id)

    file_content = process_ctrl.get_file_content(file_id=file_id)

    if file_content is None:
        logger.error(responsesignal.FILE_NOT_FOUND.value)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "signal": responsesignal.FILE_NOT_FOUND.value
            }
        )
    
    file_chunks = process_ctrl.get_file_chunks(
        file_content=file_content,
        file_id=file_id,
        chunk_size=chunk_size,
        overlap_size=overlap_size
    )

    if not file_chunks or len(file_chunks) == 0:
        logger.error(responsesignal.FILE_PROCESS_FAILED.value)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": responsesignal.FILE_PROCESS_FAILED.value
            }
        )

    logger.info(responsesignal.FILE_PROCESS_SUCCESS.value)
    return JSONResponse(
        content={
            "signal": responsesignal.FILE_PROCESS_SUCCESS.value,
            "file_id": file_id,
            "total_chunks": len(file_chunks),
            "chunk_size": chunk_size,
            "overlap_size": overlap_size,
            "file_chunks": file_chunks
        }
    )