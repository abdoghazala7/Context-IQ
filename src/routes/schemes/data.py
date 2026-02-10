from pydantic import BaseModel, field_validator
from typing import Optional
import re


class processrequest(BaseModel):
    file_id: Optional[int] = None
    chunk_size: Optional[int] = 1000
    overlap_size: Optional[int] = 200
    do_reset: Optional[int] = 0


class urlingestrequest(BaseModel):
    url: str
    chunk_size: Optional[int] = 1000
    overlap_size: Optional[int] = 200

    @field_validator("url")
    @classmethod
    def validate_url_format(cls, v: str) -> str:
        pattern = re.compile(
            r"^https?://"
            r"(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}"
            r"(?::\d+)?"
            r"(?:/[^\s]*)?$"
        )
        if not pattern.match(v):
            raise ValueError("Invalid URL format. Must start with http:// or https://")
        return v
