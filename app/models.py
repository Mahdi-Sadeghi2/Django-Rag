from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Heading(BaseModel):
    level: int = Field(..., ge=1, le=6)
    text: str


class Page(BaseModel):
    url: str
    title: str
    content: str
    headings: list[Heading] = Field(default_factory=list)
    scraped_at: datetime
    content_hash: str

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Page content cannot be empty")
        return v.strip()


class Chunk(BaseModel):
    page_url: str
    page_title: str
    content: str
    heading_path: str = ""
    chunk_index: int
    token_count: Optional[int] = None
