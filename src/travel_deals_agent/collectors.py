from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

from travel_deals_agent.models import RawItem
from travel_deals_agent.sources import AviasalesCalendarSource, RssSource


def collect_rss(source: RssSource, timeout: float = 20.0) -> list[RawItem]:
    response = httpx.get(
        str(source.url),
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": "travel-deals-agent/0.1 (+https://localhost)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    response.raise_for_status()
    parsed = feedparser.parse(response.text)

    items: list[RawItem] = []
    for entry in parsed.entries[:30]:
        published = None
        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        url = getattr(entry, "link", None)
        title = getattr(entry, "title", "").strip()
        if not url or not title:
            continue

        items.append(
            RawItem(
                source=source.name,
                title=title,
                url=url,
                summary=getattr(entry, "summary", ""),
                published_at=published,
            )
        )
    return items


def collect_aviasales_calendar(source: AviasalesCalendarSource, timeout: float = 20.0) -> list[RawItem]:
    items: list[RawItem] = []
    today = datetime.now(timezone.utc).date()
    date_from = today + timedelta(days=1)
    date_to = today + timedelta(days=max(source.lookahead_days, 1))

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": "travel-deals-agent/0.1 (+https://localhost)",
            "Accept": "application/json",
        },
    ) as client:
        for origin in source.origins:
            origin_items: list[RawItem] = []
            for destination in source.destinations:
                if origin == destination:
                    continue
                response = client.get(
                    "https://explore-api.aviasales.ru/api/v6/calendar.json",
                    params={
                        "origin_iata": origin,
                        "destination_iata": destination,
                        "origin_type": "city",
                        "destination_type": "city",
                        "brand": "AS",
                        "locale": source.locale,
                        "currency": source.currency,
                        "one_way": "true",
                        "depart_date_from": date_from.isoformat(),
                        "depart_date_to": date_to.isoformat(),
                    },
                )
                response.raise_for_status()
                origin_items.extend(
                    _items_from_aviasales_calendar_response(
                        source=source,
                        origin=origin,
                        destination=destination,
                        payload=response.json(),
                    )
                )
            items.extend(sorted(origin_items, key=_aviasales_price_from_item)[: source.limit_per_origin])
    return items


def _items_from_aviasales_calendar_response(
    source: AviasalesCalendarSource,
    origin: str,
    destination: str,
    payload: dict[str, Any],
) -> list[RawItem]:
    prices = [
        price
        for price in payload.get("prices", [])
        if price.get("state") == "EXISTS" and isinstance(price.get("price"), int) and price.get("depart_date")
    ]
    if not prices:
        return []

    best = min(prices, key=lambda price: price["price"])
    price_rub = best["price"]
    if source.max_price_rub is not None and price_rub > source.max_price_rub:
        return []

    depart_date = str(best["depart_date"])
    search_date = datetime.fromisoformat(depart_date).strftime("%d%m")
    url = f"https://www.aviasales.ru/search/{origin}{search_date}{destination}1"
    title = f"Low fare from {origin} to {destination}: {price_rub} RUB one-way on {depart_date}"
    summary = (
        "Aviasales calendar minimum price. "
        f"Route {origin}-{destination}, one-way, currency RUB, source {source.name}."
    )
    return [
        RawItem(
            source=source.name,
            title=title,
            url=url,
            summary=summary,
            published_at=datetime.now(timezone.utc),
        )
    ]


def _aviasales_price_from_item(item: RawItem) -> int:
    for part in item.title.split():
        if part.isdigit():
            return int(part)
    return 10**9
