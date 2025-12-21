from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):

    APP_NAME: str
    ALLOWED_EXTENSIONS: list[str]
    MAX_FILE_SIZE: int  # in bytes
    FILE_DEFAULT_CHUNK_SIZE: int  # in bytes

    class Config:
        env_file = ".env"

def get_config() -> Config:
    return Config()