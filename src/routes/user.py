from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import JSONResponse
from models.UserModel import UserModel
from models.enums.ResponseSignal import responsesignal
from routes.auth import get_current_user
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger('uvicorn.error')


class RegisterRequest(BaseModel):
    user_name: Optional[str] = None


user_router = APIRouter(
    prefix="/api/v1/user",
    tags=["User Management"]
)


@user_router.post("/register")
async def register_user(request: Request, register_request: RegisterRequest):
    """
    Register a new user and return their API key.
    This is the only endpoint that does NOT require authentication.
    Store the returned API key securely — it cannot be recovered.
    """
    user_model = await UserModel.create_instance(db_client=request.app.db_client)
    user = await user_model.create_user(user_name=register_request.user_name)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "signal": responsesignal.USER_CREATED_SUCCESS.value,
            "user_id": user.user_id,
            "api_key": user.user_api_key,
            "message": "Store this API key securely. Use it in the X-API-Key header for all future requests."
        }
    )


@user_router.get("/me")
async def get_current_user_info(current_user=Depends(get_current_user)):
    """
    Return the authenticated user's basic info.
    Useful for verifying that your API key is working.
    """
    return JSONResponse(
        content={
            "user_id": current_user.user_id,
            "user_name": current_user.user_name,
            "is_active": current_user.is_active,
        }
    )
