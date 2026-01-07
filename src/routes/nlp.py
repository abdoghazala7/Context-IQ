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
    project_id: str,
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
       generation_client=request.app.generation_client
   )

   has_records = True
   page_no = 1
   inserted_items_count = 0

   while has_records:
       page_chunks = await chunk_model.get_project_chunks(db_project_id=project.id, page_no=page_no)
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
async def get_project_index_info(request: Request, project_id: str):
    
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
       generation_client=request.app.generation_client
       )
    
    collection_info = nlp_controller.get_vector_db_collection_info(project=project)

    return JSONResponse(
        content={
            "signal": responsesignal.VECTORDB_COLLECTION_RETRIEVED.value,
            "collection_info": collection_info
        }
    )

@nlp_router.post("/index/search/{project_id}")
async def search_index(request: Request, project_id: str, search_request: SearchRequest):

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
       generation_client=request.app.generation_client
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
            "results": [ r.model_dump() if hasattr(r, 'model_dump') else r.dict() for r in results ]
        }
    )







   

    