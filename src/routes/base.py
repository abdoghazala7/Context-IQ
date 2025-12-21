from fastapi import APIRouter, status, Depends
from fastapi.responses import JSONResponse
from helpers.config import get_config, Config

base_router = APIRouter(
    prefix="/api/v1",
    tags=["RAG APP"]
)

@base_router.get("/")
async def welcome_and_health_check(config: Config = Depends(get_config)):

    return JSONResponse(
        content={"message": config.WELCOME_AND_HEALTH_CHECK_MESSAGE},
        status_code=status.HTTP_200_OK,
    )
