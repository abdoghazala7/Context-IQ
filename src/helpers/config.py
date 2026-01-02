from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import field_validator

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str
    ALLOWED_EXTENSIONS: list[str]
    MAX_FILE_SIZE: int  # in bytes
    FILE_DEFAULT_CHUNK_SIZE: int  # in bytes
    
    MONGODB_URL: str
    MONGODB_DATABASE: str

    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str

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