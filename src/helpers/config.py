from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):

    APP_NAME: str
    ALLOWED_EXTENSIONS: list[str]
    MAX_FILE_SIZE: int  # in bytes
    FILE_DEFAULT_CHUNK_SIZE: int  # in bytes
    
    MONGODB_URL: str
    MONGODB_DATABASE: str

    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str

    OPENAI_API_KEY: str = None
    OPENAI_API_URL: str = None
    COHERE_API_KEY: str = None

    GENERATION_MODEL_ID: str = None
    EMBEDDING_MODEL_ID: str = None
    EMBEDDING_MODEL_SIZE: int = None

    INPUT_DEFAULT_MAX_CHARACTERS: int = None
    GENERATION_DEFAULT_MAX_TOKENS: int = None
    GENERATION_DEFAULT_TEMPERATURE: float = None

    class Config:
        env_file = ".env"

def get_config() -> Config:
    return Config()