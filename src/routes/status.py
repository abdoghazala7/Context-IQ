from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from celery.result import AsyncResult
from celery_app import celery_app
from models.enums.ResponseSignal import responsesignal

import logging

logger = logging.getLogger('uvicorn.error')

status_router = APIRouter(
    prefix="/api/v1",
    tags=["Task Status"]
)


@status_router.get("/task/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Check the current status and result of a Celery task by its task_id.
    """

    try:
        task_result = AsyncResult(task_id, app=celery_app)

        response = {
            "task_id": task_id,
            "status": task_result.status,
        }

        if task_result.ready():
            # Task finished (SUCCESS or FAILURE)
            if task_result.successful():
                response["result"] = task_result.result
                response["signal"] = responsesignal.TASK_STATUS_SUCCESS.value
            else:
                # Task failed — include error info
                response["error"] = str(task_result.result)
                response["signal"] = responsesignal.TASK_STATUS_FAILED.value
        else:
            # Task still running or pending
            response["signal"] = responsesignal.TASK_STATUS_PENDING.value

            # Include progress metadata if the task reported any
            if task_result.info and isinstance(task_result.info, dict):
                response["meta"] = task_result.info

        return JSONResponse(content=response)

    except Exception as e:
        logger.error(f"Error fetching task status for {task_id}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "signal": responsesignal.TASK_STATUS_ERROR.value,
                "error": str(e)
            }
        )
