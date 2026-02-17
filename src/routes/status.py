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


def _task_exists_in_backend(task_id: str) -> bool:
    """
    Check if a task_id actually exists in the Redis result backend.
    Celery returns PENDING for both truly-pending tasks AND non-existent ones,
    so we check the Redis key directly to distinguish the two cases.
    """
    try:
        backend = celery_app.backend
        key = backend.get_key_for_task(task_id)
        return backend.client.exists(key)
    except Exception:
        # If we can't check, assume it exists to avoid false negatives
        return True


@status_router.get("/task/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Check the current status and result of a Celery task by its task_id.
    """

    try:
        task_result = AsyncResult(task_id, app=celery_app)

        # Safely get the task state - backend deserialization can fail
        # if previous results were stored in a corrupted format
        try:
            task_status = task_result.status
        except Exception as e:
            logger.warning(f"Failed to read task state for {task_id}: {e}")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "task_id": task_id,
                    "status": "UNKNOWN",
                    "signal": responsesignal.TASK_NOT_FOUND.value,
                }
            )

        response = {
            "task_id": task_id,
            "status": task_status,
        }

        if task_status == "SUCCESS":
            try:
                result = task_result.result
                # Strip internal fields before returning to user
                if isinstance(result, dict):
                    result = {k: v for k, v in result.items() if not k.startswith("_")}
                response["result"] = result
            except Exception:
                response["result"] = None
            response["signal"] = responsesignal.TASK_STATUS_SUCCESS.value

        elif task_status == "FAILURE":
            try:
                response["error"] = str(task_result.result)
            except Exception:
                response["error"] = "Task failed (details unavailable)"
            response["signal"] = responsesignal.TASK_STATUS_FAILED.value

        elif task_status == "STARTED":
            response["signal"] = responsesignal.TASK_STATUS_PENDING.value
            try:
                if task_result.info and isinstance(task_result.info, dict):
                    response["meta"] = task_result.info
            except Exception:
                pass

        elif task_status == "RETRY":
            response["signal"] = responsesignal.TASK_STATUS_PENDING.value

        elif task_status == "PENDING":
            # PENDING is Celery's default for BOTH actually-queued tasks
            # AND completely non-existent task_ids.
            # Check the result backend to distinguish the two.
            if not _task_exists_in_backend(task_id):
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={
                        "task_id": task_id,
                        "status": "UNKNOWN",
                        "signal": responsesignal.TASK_NOT_FOUND.value,
                    }
                )
            response["signal"] = responsesignal.TASK_STATUS_PENDING.value

        elif task_status == "RECEIVED":
            response["signal"] = responsesignal.TASK_STATUS_PENDING.value

        elif task_status == "REVOKED":
            response["signal"] = responsesignal.TASK_STATUS_FAILED.value
            response["error"] = "Task was revoked/cancelled"

        else:
            response["signal"] = responsesignal.TASK_STATUS_PENDING.value

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
