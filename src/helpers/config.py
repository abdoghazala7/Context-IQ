from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import field_validator
from typing import List
class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str
    ALLOWED_EXTENSIONS: list[str]
    MAX_FILE_SIZE: int  # in bytes
    FILE_DEFAULT_CHUNK_SIZE: int  # in bytes
    
    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_MAIN_DATABASE: str

    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str

    VECTOR_DB_BACKEND_LITERAL: List[str]
    VECTOR_DB_BACKEND: str
    VECTOR_DB_NAME: str
    VECTOR_DB_DISTANCE_METHOD: str
    VECTOR_DB_PGVEC_INDEX_THRESHOLD : int = 1000

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_URL: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    GENERATION_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_SIZE: Optional[int] = None

    INPUT_DEFAULT_MAX_CHARACTERS: Optional[int] = None
    GENERATION_DEFAULT_MAX_TOKENS: Optional[int] = None
    GENERATION_DEFAULT_TEMPERATURE: Optional[float] = None

    PRIMARY_LANG: str = "en"
    DEFAULT_LANG: str = "en"

    @field_validator(
        'OPENAI_API_KEY', 'OPENAI_API_URL', 'COHERE_API_KEY', 'GROQ_API_KEY',
        'GENERATION_MODEL_ID', 'EMBEDDING_MODEL_ID', 'EMBEDDING_MODEL_SIZE',
        'INPUT_DEFAULT_MAX_CHARACTERS', 'GENERATION_DEFAULT_MAX_TOKENS',
        'GENERATION_DEFAULT_TEMPERATURE', mode='before'
    )
    @classmethod
    def empty_str_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

def get_config() -> Config:
    return Config()
