from fastapi import APIRouter, Depends, status, Request
from fastapi.responses import JSONResponse
from routes.schemes.nlp import PushRequest, SearchRequest
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from controllers import NLPController
from helpers.config import get_config
from models import responsesignal
from tasks.data_indexing import index_data_content
from routes.auth import get_current_user

import logging

logger = logging.getLogger('uvicorn.error')

settings = get_config()

nlp_router = APIRouter(
    prefix="/api/v1/nlp",  
    tags=["NLP Operations"]
)

@nlp_router.post("/index/push/{project_id}")
async def push_index(
    request: Request,
    project_id: int,
    push_request: PushRequest,
    current_user = Depends(get_current_user)
):
   
   """Endpoint to push NLP index data for a specific project."""

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
   
   chunk_model = await ChunkModel.create_instance(db_client=request.app.db_client)
   total_chunks_count = await chunk_model.get_total_chunks_count(project_id=project_id)

   task = index_data_content.delay(
        project_id=project_id,
        do_reset=push_request.do_reset,
        total_chunks_count=total_chunks_count 
    )

   return JSONResponse(
        content={
            "signal": responsesignal.PROCESS_AND_PUSH_READY.value,
            "task_id": task.id
        }
    )



@nlp_router.get("/index/info/{project_id}")
async def get_project_index_info(
    request: Request,
    project_id: int,
    current_user = Depends(get_current_user)
):
    
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_user_project(
        project_id=project_id,
        user_id=current_user.user_id
    )

    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": responsesignal.PROJECT_NOT_FOUND_ERROR.value
            }
        )
   
    nlp_controller = NLPController(
       vectordb_client=request.app.vectordb_client,
       generation_client=request.app.generation_client,
        template_parser=request.app.template_parser,
        embedding_client=request.app.embedding_client,

       )
    
    collection_info = await nlp_controller.get_vector_db_collection_info(project=project)

    return JSONResponse(
        content={
            "signal": responsesignal.VECTORDB_COLLECTION_RETRIEVED.value,
            "collection_info": collection_info
        }
    )

@nlp_router.post("/index/search/{project_id}")
async def search_index(
    request: Request,
    project_id: int,
    search_request: SearchRequest,
    current_user = Depends(get_current_user)
):

    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_user_project(
        project_id=project_id,
        user_id=current_user.user_id
    )

    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": responsesignal.PROJECT_NOT_FOUND_ERROR.value
            }
        )
   
    nlp_controller = NLPController(
       vectordb_client=request.app.vectordb_client,
       generation_client=request.app.generation_client,
       template_parser=request.app.template_parser,
       embedding_client=request.app.embedding_client,
       )
    
    results = await nlp_controller.search_vector_db_collection(
        project=project,
        text=search_request.text,
        limit=search_request.limit,
        score_threshold=search_request.score_threshold
    )

    if not results:
        return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": responsesignal.VECTORDB_SEARCH_ERROR.value
                }
            )
    
    return JSONResponse(
        content={
            "signal": responsesignal.VECTORDB_SEARCH_SUCCESS.value,
            "results": [ result.dict()  for result in results ]
        }
    )

@nlp_router.post("/index/answer/{project_id}")
async def answer_index(
    request: Request,
    project_id: int,
    search_request: SearchRequest,
    current_user = Depends(get_current_user)
):

    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_user_project(
        project_id=project_id,
        user_id=current_user.user_id
    )

    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": responsesignal.PROJECT_NOT_FOUND_ERROR.value
            }
        )
   
    nlp_controller = NLPController(
       vectordb_client=request.app.vectordb_client,
       generation_client=request.app.generation_client,
       template_parser=request.app.template_parser,
       embedding_client=request.app.embedding_client,
       )
    
    answer, full_prompt, chat_history = await nlp_controller.answer_rag_question(
        project=project,
        query=search_request.text,
        limit=search_request.limit,
        score_threshold=search_request.score_threshold,
        primary_lang=search_request.primary_lang
    )

    if not answer:
        return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": responsesignal.RAG_ANSWER_ERROR.value
                }
        )
    
    return JSONResponse(
        content={
            "signal": responsesignal.RAG_ANSWER_SUCCESS.value,
            "answer": answer,
            "full_prompt": full_prompt,
            "chat_history": chat_history
        }
    )