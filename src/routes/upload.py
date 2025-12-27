from fastapi import FastAPI, APIRouter, Depends, File, UploadFile, status, Request
from controllers import uploadcontroller, processcontroller
from fastapi.responses import JSONResponse
from helpers.config import Config , get_config
from models import responsesignal
from routes.schemes import processrequest
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from models.db_schemes import DataChunk
from models.enums.ResponseSignal import responsesignal
import aiofiles
import logging


logger = logging.getLogger('uvicorn.error')

Data_router = APIRouter(
    prefix="/api/v1",  
    tags=["File Upload"]
)

@Data_router.post("/upload/{project_id}")
async def upload_file(
    request: Request,
    project_id : str,
    file: UploadFile = File(...),
    config: Config = Depends(get_config)
):
    """
    Endpoint to upload a file for a specific project.
    """

    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(project_id=project_id)

    # validate the file properties
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
    request: Request,
    project_id: str,
    process_request: processrequest
):

    file_id = process_request.file_id
    chunk_size = process_request.chunk_size
    overlap_size = process_request.overlap_size
    do_reset = process_request.do_reset

    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(project_id=project_id)

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
                "signal": responsesignal.PROCESSING_FAILED.value
            }
        )
  
    file_chunks_records = [
        DataChunk(
            chunk_text=chunk.page_content,
            chunk_metadata=chunk.metadata,
            chunk_order=i+1,
            chunk_project_id=project.id,
        )
        for i, chunk in enumerate(file_chunks)
    ]

    chunk_model = await ChunkModel.create_instance(
        db_client=request.app.db_client
    )

    if do_reset == 1:
        _ = await chunk_model.delete_chunks_by_db_project_id(
            db_project_id=project.id
        )

    no_records = await chunk_model.insert_many_chunks(chunks=file_chunks_records)

    return JSONResponse(
        content={
            "signal": responsesignal.PROCESSING_SUCCESS.value,
            "inserted_chunks": no_records
        }
    )