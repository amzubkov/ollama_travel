import json
from pathlib import Path

from pydantic import BaseModel, HttpUrl


class RssSource(BaseModel):
    name: str
    url: HttpUrl


class Watchlist(BaseModel):
    origins: list[str] = []
    destinations: list[str] = []
    keywords: list[str] = []


class SourceConfig(BaseModel):
    rss: list[RssSource] = []
    watchlist: Watchlist = Watchlist()


def load_sources(path: Path) -> SourceConfig:
    with path.open("r", encoding="utf-8") as f:
        return SourceConfig.model_validate(json.load(f))
