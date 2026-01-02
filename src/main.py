from fastapi import FastAPI
from routes.base import Base_router
from routes.upload import Data_router
from motor.motor_asyncio import AsyncIOMotorClient
from helpers.config import Config
from contextlib import asynccontextmanager
from stores.llm import LLMProviderFactory

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = Config()
    app.mongo_conn = AsyncIOMotorClient(settings.MONGODB_URL)
    app.db_client = app.mongo_conn[settings.MONGODB_DATABASE]

    llm_provider_factory = LLMProviderFactory(settings)

    #  # generation client
    app.generation_client = llm_provider_factory.create(provider=settings.GENERATION_BACKEND)
    app.generation_client.set_generation_model(model_id = settings.GENERATION_MODEL_ID)
    app.generation_client.set_embedding_model(model_id = settings.EMBEDDING_MODEL_ID)

    
    yield
    
    # Shutdown
    app.mongo_conn.close()

app = FastAPI(lifespan=lifespan)
    
app.include_router(Base_router)
app.include_router(Data_router)