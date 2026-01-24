from fastapi import FastAPI
from routes.base import Base_router
from routes.upload import Data_router
from routes.nlp import nlp_router
from helpers.config import Config
from contextlib import asynccontextmanager
from stores.llm import LLMProviderFactory
from stores.vectordb import VectorDBProviderFactory
from stores.llm.templates.template_parser import TemplateParser
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import metrics setup
from utils.metrics import setup_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = Config()

    postgres_conn = f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DATABASE}"
    app.db_engine = create_async_engine(postgres_conn)
    app.db_client = sessionmaker(
        app.db_engine, class_=AsyncSession, expire_on_commit=False
    )

    llm_provider_factory = LLMProviderFactory(settings)
    vectordb_provider_factory = VectorDBProviderFactory(config=settings, db_client=app.db_client)

    #  # generation client
    app.generation_client = llm_provider_factory.create(provider=settings.GENERATION_BACKEND)
    app.generation_client.set_generation_model(model_id = settings.GENERATION_MODEL_ID)
    app.generation_client.set_embedding_model(model_id = settings.EMBEDDING_MODEL_ID)

    # vector db client
    app.vectordb_client = vectordb_provider_factory.create(provider=settings.VECTOR_DB_BACKEND)
    await app.vectordb_client.connect()

    # template parser
    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANG,
        default_language=settings.DEFAULT_LANG,
    )

    
    yield
    
    # Shutdown
    app.db_engine.dispose()
    await app.vectordb_client.disconnect()

app = FastAPI(lifespan=lifespan)
# Setup Prometheus metrics
setup_metrics(app)
    
app.include_router(Base_router)
app.include_router(Data_router)
app.include_router(nlp_router)
