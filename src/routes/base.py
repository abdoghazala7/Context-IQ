from fastapi import APIRouter, status, Depends
from fastapi.responses import JSONResponse
from models import responsesignal

base_router = APIRouter(
    prefix="/api/v1",
    tags=["RAG APP"]
)

@base_router.get("/")
async def welcome_and_health_check(signal: responsesignal=responsesignal.WELCOME_AND_HEALTH_CHECK_MESSAGE.value):

    return JSONResponse(
        content={"message": signal},
        status_code=status.HTTP_200_OK,
    )
