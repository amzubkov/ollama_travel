from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import feedparser
import httpx

from travel_deals_agent.models import RawItem
from travel_deals_agent.sources import (
    AviasalesCalendarSource,
    AviasalesExactTripSource,
    RssSource,
    TrackedHotelStaySource,
)


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


def collect_aviasales_exact_trip(source: AviasalesExactTripSource, timeout: float = 20.0) -> list[RawItem]:
    depart_date_to = source.return_date or source.depart_date
    response = httpx.get(
        "https://explore-api.aviasales.ru/api/v6/calendar.json",
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": "travel-deals-agent/0.1 (+https://localhost)",
            "Accept": "application/json",
        },
        params={
            "origin_iata": source.origin,
            "destination_iata": source.destination,
            "origin_type": "city",
            "destination_type": "city",
            "brand": "AS",
            "locale": source.locale,
            "currency": source.currency,
            "one_way": "false" if source.return_date else "true",
            "depart_date_from": source.depart_date,
            "depart_date_to": depart_date_to,
        },
    )
    response.raise_for_status()
    return _items_from_aviasales_exact_trip_response(source, response.json())


def collect_tracked_hotel_stay(source: TrackedHotelStaySource) -> list[RawItem]:
    params = [
        ("checkin", source.checkin),
        ("checkout", source.checkout),
        ("adults", str(source.adults)),
    ]
    if source.location_id is not None:
        params.insert(0, ("location_type", "city"))
        params.insert(0, ("location_id", str(source.location_id)))
    else:
        params.insert(0, ("location", source.city))
    if source.max_price_rub is not None:
        params.append(("price_max", str(source.max_price_rub)))
    if source.min_rating is not None:
        params.append(("rating_min", f"{source.min_rating:g}"))

    query = urlencode(params)
    url = f"https://www.aviasales.ru/hotels/search?{query}"
    constraints = []
    if source.max_price_rub is not None:
        constraints.append(f"max {source.max_price_rub} RUB/night")
    if source.min_rating is not None:
        constraints.append(f"rating >= {source.min_rating:g}/10")
    constraints_text = f", {', '.join(constraints)}" if constraints else ""
    title = (
        f"Tracked hotel stay: {source.city}, {source.checkin} to {source.checkout}, "
        f"{source.adults} adults{constraints_text}"
    )
    summary = (
        "Tracked hotel search link. Price is not extracted yet; "
        f"open the link to compare current hotel offers{constraints_text}."
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


def _items_from_aviasales_exact_trip_response(
    source: AviasalesExactTripSource,
    payload: dict[str, Any],
) -> list[RawItem]:
    prices = [
        price
        for price in payload.get("prices", [])
        if price.get("state") == "EXISTS"
        and isinstance(price.get("price"), int)
        and price.get("price", 0) > 0
        and price.get("depart_date") == source.depart_date
        and price.get("return_date") == source.return_date
    ]
    if not prices:
        return []

    best = min(prices, key=lambda price: price["price"])
    price_rub = best["price"]
    if source.max_price_rub is not None and price_rub > source.max_price_rub:
        return []

    origin_name = source.origin_name or source.origin
    destination_name = source.destination_name or source.destination
    depart_search = datetime.fromisoformat(source.depart_date).strftime("%d%m")
    if source.return_date:
        return_search = datetime.fromisoformat(source.return_date).strftime("%d%m")
        search_path = f"{source.origin}{depart_search}{source.destination}{return_search}1"
        date_text = f"{source.depart_date} to {source.return_date}"
        trip_type = "round-trip"
    else:
        search_path = f"{source.origin}{depart_search}{source.destination}1"
        date_text = source.depart_date
        trip_type = "one-way"

    url = f"https://www.aviasales.ru/search/{search_path}"
    title = (
        f"Tracked trip: {origin_name} ({source.origin}) to {destination_name} ({source.destination}), "
        f"{date_text}: {price_rub} RUB {trip_type}"
    )
    summary = (
        "Exact Aviasales calendar match. "
        f"Route {source.origin}-{source.destination}, dates {date_text}, currency RUB."
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
