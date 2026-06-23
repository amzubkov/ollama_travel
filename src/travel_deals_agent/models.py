from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class RawItem(BaseModel):
    source: str
    title: str
    url: HttpUrl
    summary: str = ""
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DealAnalysis(BaseModel):
    category: str = "unknown"
    score: int = Field(ge=0, le=100)
    summary: str
    extracted_terms: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    is_alert_worthy: bool = False


class StoredDeal(BaseModel):
    id: int | None = None
    source: str
    title: str
    url: str
    summary: str
    published_at: str | None = None
    score: int = 0
    analysis: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
