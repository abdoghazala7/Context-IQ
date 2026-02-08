from pydantic import BaseModel, field_validator
from typing import Optional
from helpers.config import get_config

settings = get_config()

class PushRequest(BaseModel):
    do_reset: Optional[int] = 0

class SearchRequest(BaseModel):
    text: str
    limit: Optional[int] = 5
    score_threshold: Optional[float] = None
    primary_lang: Optional[str] = None

    @field_validator('primary_lang')
    @classmethod
    def validate_primary_lang(cls, v: str) -> str:
        if v is not None:
            supported_langs = ['en', 'ar']
            if v.strip().lower() not in supported_langs:
                raise ValueError(
                    f'Unsupported language: {v}. '
                    f'Supported languages are: {", ".join(supported_langs)}'
                )
            return v.strip().lower()
        return v

    @field_validator('text')
    @classmethod
    def validate_text_length(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('text field cannot be empty or contain only whitespace')
        
        max_chars = settings.INPUT_DEFAULT_MAX_CHARACTERS or 1200
        if len(v) > max_chars:
            raise ValueError(
                f'text exceeds maximum length of {max_chars} characters. '
                f'Current length: {len(v)} characters. '
                f'Please shorten your input.'
            )
        return v.strip()