import json
from pathlib import Path

from pydantic import BaseModel, HttpUrl


class RssSource(BaseModel):
    name: str
    url: HttpUrl


class AviasalesCalendarSource(BaseModel):
    name: str = "Aviasales Calendar"
    origins: list[str] = []
    destinations: list[str] = []
    currency: str = "rub"
    locale: str = "ru_RU"
    max_price_rub: int | None = None
    lookahead_days: int = 90
    limit_per_origin: int = 30


class AviasalesExactTripSource(BaseModel):
    name: str = "Aviasales Exact Trip"
    origin: str
    destination: str
    origin_name: str = ""
    destination_name: str = ""
    depart_date: str
    return_date: str | None = None
    currency: str = "rub"
    locale: str = "ru_RU"
    max_price_rub: int | None = None


class TrackedHotelStaySource(BaseModel):
    name: str = "Tracked Hotel Stay"
    city: str
    location_id: int | None = None
    checkin: str
    checkout: str
    adults: int = 2
    max_price_rub: int | None = None
    min_rating: float | None = None


class Watchlist(BaseModel):
    origins: list[str] = []
    destinations: list[str] = []
    keywords: list[str] = []
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []
    hotel_keywords: list[str] = []
    hotel_region_keywords: list[str] = []
    min_hotel_discount_percent: int = 50
    cruise_keywords: list[str] = []
    cruise_region_keywords: list[str] = []
    min_cruise_discount_percent: int = 50


class SourceConfig(BaseModel):
    rss: list[RssSource] = []
    aviasales_calendar: list[AviasalesCalendarSource] = []
    aviasales_exact_trips: list[AviasalesExactTripSource] = []
    tracked_hotel_stays: list[TrackedHotelStaySource] = []
    watchlist: Watchlist = Watchlist()


def load_sources(path: Path) -> SourceConfig:
    with path.open("r", encoding="utf-8") as f:
        return SourceConfig.model_validate(json.load(f))
