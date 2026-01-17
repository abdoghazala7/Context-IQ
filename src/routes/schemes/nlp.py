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

    @field_validator('text')
    @classmethod
    def validate_text_length(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('text field cannot be empty or contain only whitespace')
        
        max_chars = settings.INPUT_DEFAULT_MAX_CHARACTERS or 2000
        if len(v) > max_chars:
            raise ValueError(
                f'text exceeds maximum length of {max_chars} characters. '
                f'Current length: {len(v)} characters. '
                f'Please shorten your input.'
            )
        return v.strip()