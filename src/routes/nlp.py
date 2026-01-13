from fastapi import FastAPI, APIRouter, status, Request
from fastapi.responses import JSONResponse
from routes.schemes.nlp import PushRequest, SearchRequest
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from controllers import NLPController

from models import responsesignal

import logging

logger = logging.getLogger('uvicorn.error')

nlp_router = APIRouter(
    prefix="/api/v1/nlp",  
    tags=["NLP Operations"]
)

@nlp_router.post("/index/push/{project_id}")
async def push_index(
    request: Request,
    project_id: int,
    push_request: PushRequest
):
   
   """Endpoint to push NLP index data for a specific project."""

   project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

   chunk_model = await ChunkModel.create_instance(
        db_client=request.app.db_client
    )

   project = await project_model.get_project_or_create_one(
        project_id=project_id
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
   )

   has_records = True
   page_no = 1
   inserted_items_count = 0

   while has_records:
       page_chunks = await chunk_model.get_project_chunks(db_project_id=project_id, page_no=page_no)
       if len(page_chunks):
           page_no += 1
       
       if not page_chunks or len(page_chunks) == 0:
           has_records = False
           break

       
       is_inserted = nlp_controller.index_into_vector_db(
           project=project,
           chunks=page_chunks,
           do_reset=push_request.do_reset
       )

       if not is_inserted:
           return JSONResponse(
               status_code=status.HTTP_400_BAD_REQUEST,
               content={
                   "signal": responsesignal.INSERT_INTO_VECTORDB_ERROR.value
               }
           )
       
       inserted_items_count += len(page_chunks)
       
   return JSONResponse(
       content={
           "signal": responsesignal.INSERT_INTO_VECTORDB_SUCCESS.value,
           "inserted_items_count": inserted_items_count
       }
   )

@nlp_router.get("/index/info/{project_id}")
async def get_project_index_info(request: Request, project_id: int):
    
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
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

       )
    
    collection_info = nlp_controller.get_vector_db_collection_info(project=project)

    return JSONResponse(
        content={
            "signal": responsesignal.VECTORDB_COLLECTION_RETRIEVED.value,
            "collection_info": collection_info
        }
    )

@nlp_router.post("/index/search/{project_id}")
async def search_index(request: Request, project_id: int, search_request: SearchRequest):

    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
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
       )
    
    results = nlp_controller.search_vector_db_collection(
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
async def search_index(request: Request, project_id: int, search_request: SearchRequest):

    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
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
       )
    
    answer, full_prompt, chat_history = nlp_controller.answer_rag_question(
        project=project,
        query=search_request.text,
        limit=search_request.limit,
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