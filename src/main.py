from fastapi import FastAPI
from routes.base import Base_router
from routes.upload import Data_router
from routes.nlp import nlp_router
from motor.motor_asyncio import AsyncIOMotorClient
from helpers.config import Config
from contextlib import asynccontextmanager
from stores.llm import LLMProviderFactory
from stores.vectordb import VectorDBProviderFactory
from stores.llm.templates.template_parser import TemplateParser

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = Config()
    app.mongo_conn = AsyncIOMotorClient(settings.MONGODB_URL)
    app.db_client = app.mongo_conn[settings.MONGODB_DATABASE]

    llm_provider_factory = LLMProviderFactory(settings)
    vectordb_provider_factory = VectorDBProviderFactory(settings)

    #  # generation client
    app.generation_client = llm_provider_factory.create(provider=settings.GENERATION_BACKEND)
    app.generation_client.set_generation_model(model_id = settings.GENERATION_MODEL_ID)
    app.generation_client.set_embedding_model(model_id = settings.EMBEDDING_MODEL_ID)

    # vector db client
    app.vectordb_client = vectordb_provider_factory.create(provider=settings.VECTOR_DB_BACKEND)
    app.vectordb_client.connect()

    # template parser
    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANG,
        default_language=settings.DEFAULT_LANG,
    )

    
    yield
    
    # Shutdown
    app.mongo_conn.close()
    app.vectordb_client.disconnect()

app = FastAPI(lifespan=lifespan)
    
app.include_router(Base_router)
app.include_router(Data_router)
app.include_router(nlp_router)
