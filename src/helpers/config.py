from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):

    WELCOME_AND_HEALTH_CHECK_MESSAGE: str 

    class Config:
        env_file = ".env"

def get_config() -> Config:
    return Config()