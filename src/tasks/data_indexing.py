from celery_app import celery_app, get_setup_utils
from helpers.config import get_config
import asyncio
import uuid
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from controllers import NLPController
from tqdm.auto import tqdm
from models import responsesignal
from utils.idempotency_manager import IdempotencyManager

import logging
logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True, name="tasks.data_indexing.index_data_content",
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def index_data_content(self, project_id: int, do_reset: int, total_chunks_count: int):
    return asyncio.run(
        _index_data_content(self, project_id, do_reset, total_chunks_count)
    )

async def _index_data_content(task_instance, project_id: int, do_reset: int, total_chunks_count: int):
    
    db_engine, vectordb_client = None, None
    idempotency_manager = None
    task_record = None 
    settings = get_config()

    try:
        (db_engine, db_client, llm_provider_factory, 
        vectordb_provider_factory,
        generation_client, embedding_client,
        vectordb_client, template_parser) = await get_setup_utils()
        
        idempotency_manager = IdempotencyManager(db_client, db_engine)

        task_args = {
            "project_id": project_id,
            "do_reset": do_reset,
            "total_chunks_count": total_chunks_count
        }
        
        task_name = "tasks.data_indexing.index_data_content"
        
        # Check execution
        should_execute, existing_task = await idempotency_manager.should_execute_task(
            task_name=task_name,
            task_args=task_args,
            task_time_limit=settings.CELERY_TASK_TIME_LIMIT
        )

        if not should_execute:
            logger.warning(f"Skipping task | status: {existing_task.status}")
            return existing_task.result
        
        if existing_task:
            await idempotency_manager.update_task_status(
                execution_id=existing_task.execution_id,
                status='PENDING'
            )
            task_record = existing_task
        else:
            task_record = await idempotency_manager.create_task_record(
                task_name=task_name,
                task_args=task_args,
                celery_task_id = uuid.UUID(task_instance.request.id) if task_instance.request.id else None
            )
        
        await idempotency_manager.update_task_status(
            execution_id=task_record.execution_id,
            status='STARTED'
        )
        
        # --- Start Logic ---
        project_model = await ProjectModel.create_instance(db_client=db_client)
        chunk_model = await ChunkModel.create_instance(db_client=db_client)

        project = await project_model.get_project_or_create_one(project_id=project_id)

        if not project:
            error_signal = responsesignal.PROJECT_NOT_FOUND_ERROR.value
            
            task_instance.update_state(
                state="FAILURE",
                meta={"signal": error_signal}
            )

            await idempotency_manager.update_task_status(
                execution_id=task_record.execution_id,
                status='FAILURE',
                result={"signal": error_signal}
            )

            raise Exception(f"No project found for project_id: {project_id}")
        
        nlp_controller = NLPController(
            vectordb_client=vectordb_client,
            generation_client=generation_client,
            template_parser=template_parser,
            embedding_client=embedding_client,
        )

        has_records = True
        page_no = 1
        inserted_items_count = 0

        collection_name = nlp_controller.create_collection_name(project_id=project.project_id)

        _ = await vectordb_client.create_collection(
                collection_name=collection_name,
                embedding_size=settings.EMBEDDING_MODEL_SIZE,
                do_reset=do_reset,
            )

        total_chunks_count = await chunk_model.get_total_chunks_count(project_id=project.project_id)
        pbar = tqdm(total=total_chunks_count, desc="Vector Indexing", position=0)
        logger.info(f"Vector Indexing progress: {inserted_items_count}/{total_chunks_count}")

        while has_records:
            page_chunks = await chunk_model.get_project_chunks(db_project_id=project.project_id, page_no=page_no)
            
            if len(page_chunks):
                page_no += 1
            
            if not page_chunks or len(page_chunks) == 0:
                has_records = False
                break

            chunks_ids = [c.chunk_id for c in page_chunks]

            is_inserted = await nlp_controller.index_into_vector_db(
                project=project,
                chunks=page_chunks,
                chunks_ids=chunks_ids
            )

            if not is_inserted:
                error_signal = responsesignal.INSERT_INTO_VECTORDB_ERROR.value
                
                task_instance.update_state(
                    state="FAILURE",
                    meta={"signal": error_signal}
                )
                
                await idempotency_manager.update_task_status(
                    execution_id=task_record.execution_id,
                    status='FAILURE',
                    result={"signal": error_signal}
                )

                raise Exception(f"can not insert into vectorDB | project_id: {project_id}")
            
            pbar.update(len(page_chunks))
            inserted_items_count += len(page_chunks)
            
        success_result = {
            "signal": responsesignal.INSERT_INTO_VECTORDB_SUCCESS.value,
            "inserted_items_count": inserted_items_count
        }

        task_instance.update_state(
                state="SUCCESS",
                meta=success_result
            )
        
        await idempotency_manager.update_task_status(
            execution_id=task_record.execution_id,
            status='SUCCESS',
            result=success_result 
        )
        
        return success_result
        
    except Exception as e:
        logger.error(f"Task failed: {str(e)}")
        
        if idempotency_manager and task_record:
            try:
                await idempotency_manager.update_task_status(
                    execution_id=task_record.execution_id,
                    status='FAILURE',
                    result={"error": str(e)}
                )
            except Exception as update_error:
                logger.error(f"Failed to update idempotency status: {update_error}")
        
        raise 
        
    finally:
        try:
            if db_engine:
                await db_engine.dispose()
            
            if vectordb_client:
                await vectordb_client.disconnect()
        except Exception as e:
            logger.error(f"Task failed while cleaning: {str(e)}")