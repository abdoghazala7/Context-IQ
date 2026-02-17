from celery import chain
from celery_app import celery_app, get_setup_utils
from helpers.config import get_config
import asyncio
from tasks.file_processing import process_project_files
from tasks.data_indexing import index_data_content 
from models.ChunkModel import ChunkModel 

import logging
logger = logging.getLogger(__name__)

@celery_app.task(
    bind=True, name="tasks.process_workflow.push_after_process_task",
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def push_after_process_task(self, prev_task_result):

    db_id = prev_task_result.get("_db_id")
    user_project_id = prev_task_result.get("project_id")
    do_reset = prev_task_result.get("do_reset")
    
    async def get_total_count():
         db_engine = None
         vectordb_client = None
         try:
             (db_engine, db_client, _, _,
              _, _, vectordb_client, _) = await get_setup_utils()
             chunk_model = await ChunkModel.create_instance(db_client=db_client)
             count = await chunk_model.get_total_chunks_count(project_id=db_id)
             return count
         finally:
             if db_engine:
                 await db_engine.dispose()
             if vectordb_client:
                 await vectordb_client.disconnect()

    total_chunks_count = asyncio.run(get_total_count())

    result = index_data_content.delay(
        project_id=db_id, 
        do_reset=do_reset,
        total_chunks_count=total_chunks_count 
    )

    return {
        "project_id": user_project_id,
        "do_reset": do_reset,
        "triggered_indexing_task_id": result.id, 
        "status": "Indexing Triggered"
    }

@celery_app.task(
    bind=True, name="tasks.process_workflow.process_and_push_workflow",
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def process_and_push_workflow(self, project_id: int, 
                              file_id: int, chunk_size: int,
                              overlap_size: int, do_reset: int,
                              files_state_version: int = 0):

    workflow = chain(
        process_project_files.s(project_id, file_id, chunk_size, overlap_size, do_reset,files_state_version),
        push_after_process_task.s()
    )

    result = workflow.apply_async()

    return {
        "signal": "WORKFLOW_STARTED",
        "workflow_id": result.id,
        "tasks": ["tasks.file_processing.process_project_files", 
                  "tasks.process_workflow.push_after_process_task"]
    }