from fastapi import Request, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from models.UserModel import UserModel
import logging

logger = logging.getLogger('uvicorn.error')

header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_user(
                            request: Request,
                            api_key: str = Depends(header_scheme)):
    """
    FastAPI dependency that authenticates a user via the X-API-Key header.
    
    Returns the authenticated User object.
    Raises HTTP 401 if the key is missing or invalid.
    """

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Please provide the X-API-Key header."
        )

    user_model = await UserModel.create_instance(db_client=request.app.db_client)
    user = await user_model.get_user_by_api_key(api_key=api_key)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API Key."
        )

    return user
