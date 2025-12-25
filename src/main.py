from fastapi import FastAPI
from routes.base import Base_router
from routes.upload import Data_router
from motor.motor_asyncio import AsyncIOMotorClient
from helpers.config import Config

app = FastAPI()

@app.on_event("startup")
async def startup_db_client():
    settings = Config()
    app.mongo_conn = AsyncIOMotorClient(settings.MONGODB_URL)
    app.db_client = app.mongo_conn[settings.MONGODB_DATABASE]

@app.on_event("shutdown")
async def shutdown_db_client():
    app.mongo_conn.close()

    
app.include_router(Base_router)
app.include_router(Data_router)