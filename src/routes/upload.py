from fastapi import APIRouter, Depends, File, UploadFile, status, Request
from controllers import uploadcontroller
from fastapi.responses import JSONResponse
from helpers.config import Config , get_config
from routes.schemes import processrequest
from models.ProjectModel import ProjectModel
from models.enums.ResponseSignal import responsesignal
from models.db_schemes import Asset
from models.AssetModel import AssetModel
from models.enums.AssetTypeEnum import AssetTypeEnum
from tasks.file_processing import process_project_files
from tasks.process_workflow import process_and_push_workflow
from routes.auth import get_current_user
import os
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
    project_id : int,
    file: UploadFile = File(..., description="📄 Upload your file here. Supported formats: PDF (.pdf), Word (.doc, .docx), Text (.txt)"),
    config: Config = Depends(get_config),
    current_user = Depends(get_current_user)
):
    """
    Endpoint to upload a file for a specific project.
    
    **Supported File Types:**
    - 📕 PDF files (.pdf)
    - 📘 Word documents (.doc, .docx)
    - 📄 Text files (.txt)
    
    **Note:** Requires authentication via X-API-Key header.
    """

    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(
        project_id=project_id,
        user_id=current_user.user_id
    )

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
    

    # create asset record in the database
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    asset_resource = Asset(
        asset_project_id=project.project_id,
        asset_type=AssetTypeEnum.FILE.value,
        asset_name=file_id,
        asset_size=os.path.getsize(file_path)
    )
    
    asset_record = await asset_model.create_asset(asset=asset_resource)

    return JSONResponse(
            content={
                "signal": responsesignal.FILE_UPLOAD_SUCCESS.value,
                "file_id": str(asset_record.asset_id)
            }
        )



@Data_router.post("/process/{project_id}")
async def process_file(
    request: Request,
    project_id: int,
    process_request: processrequest,
    current_user = Depends(get_current_user)
):

    # Verify that the project belongs to this user
    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_user_project(
        project_id=project_id,
        user_id=current_user.user_id
    )

    if not project:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "signal": responsesignal.PROJECT_ACCESS_DENIED.value
            }
        )

    chunk_size = process_request.chunk_size
    overlap_size = process_request.overlap_size
    do_reset = process_request.do_reset
    
    files_state_version = 0  
    
    if process_request.file_id is None:
        asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
        files_state_version = await asset_model.get_project_files_count(project_id=project_id)
    
    task = process_project_files.delay(
        project_id=project_id,
        file_id=process_request.file_id,
        chunk_size=chunk_size,
        overlap_size=overlap_size,
        do_reset=do_reset,
        files_state_version=files_state_version  
    )

    return JSONResponse(
        content={
            "signal": responsesignal.PROCESS_AND_PUSH_READY.value,
            "task_id": task.id
        }
    )
    
@Data_router.post("/process-and-push/{project_id}")
async def process_and_push_endpoint(
    request: Request,
    project_id: int,
    process_request: processrequest,
    current_user = Depends(get_current_user)
):

    # Verify that the project belongs to this user
    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_user_project(
        project_id=project_id,
        user_id=current_user.user_id
    )

    if not project:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "signal": responsesignal.PROJECT_ACCESS_DENIED.value
            }
        )

    chunk_size = process_request.chunk_size
    overlap_size = process_request.overlap_size
    do_reset = process_request.do_reset

    files_state_version = 0 
    
    if process_request.file_id is None:
        asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
        files_state_version = await asset_model.get_project_files_count(project_id=project_id)

    workflow_task = process_and_push_workflow.delay(
        project_id=project_id,
        file_id=process_request.file_id,
        chunk_size=chunk_size,
        overlap_size=overlap_size,
        do_reset=do_reset,
        files_state_version=files_state_version  
    )

    return JSONResponse(
        content={
            "signal": responsesignal.PROCESS_AND_PUSH_WORKFLOW_READY.value,
            "workflow_task_id": workflow_task.id
        }
    )