from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlencode, urljoin

import feedparser
import httpx

from travel_deals_agent.models import RawItem
from travel_deals_agent.sources import (
    AviasalesCalendarSource,
    AviasalesExactTripSource,
    BookingHotelSearchSource,
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


def collect_booking_hotel_search(source: BookingHotelSearchSource, timeout: float = 30.0) -> list[RawItem]:
    url = _booking_search_url(source)
    response = httpx.get(
        url,
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response.raise_for_status()
    html = response.text
    if "__challenge" in html or "verify that you're not a robot" in html.lower():
        raise RuntimeError("Booking challenge page returned; skipping scrape without bypass")

    cards = _parse_booking_hotel_cards(html)
    items: list[RawItem] = []
    for card in cards:
        price_rub = card.get("price_rub")
        rating = card.get("rating")
        if source.max_price_rub is not None and (price_rub is None or price_rub > source.max_price_rub):
            continue
        if source.min_rating is not None and (rating is None or rating < source.min_rating):
            continue

        title_parts = [
            f"Tracked hotel Booking: {card['title']}",
            f"{source.city}",
            f"{source.checkin} to {source.checkout}",
        ]
        if price_rub is not None:
            title_parts.append(f"{price_rub} RUB/night")
        if rating is not None:
            title_parts.append(f"rating {rating:g}/10")
        min_rating_text = f"{source.min_rating:g}/10" if source.min_rating is not None else "-"
        summary = (
            f"Booking scrape match for {source.city}, {source.adults} adults, {source.rooms} room(s). "
            f"Criteria: max {source.max_price_rub or '-'} RUB/night, rating >= {min_rating_text}."
        )
        items.append(
            RawItem(
                source=source.name,
                title=", ".join(title_parts),
                url=card.get("url") or url,
                summary=summary,
                published_at=datetime.now(timezone.utc),
            )
        )

    return sorted(items, key=_booking_item_sort_key)[: source.limit]


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


def _booking_search_url(source: BookingHotelSearchSource) -> str:
    params = {
        "ss": source.city,
        "checkin": source.checkin,
        "checkout": source.checkout,
        "group_adults": str(source.adults),
        "no_rooms": str(source.rooms),
        "group_children": "0",
        "selected_currency": source.currency,
        "order": "review_score_and_price",
    }
    if source.min_rating is not None:
        params["nflt"] = f"review_score={int(source.min_rating * 10)}"
    return f"https://www.booking.com/searchresults.html?{urlencode(params)}"


def _parse_booking_hotel_cards(html: str) -> list[dict[str, Any]]:
    parser = _BookingHotelCardParser()
    parser.feed(html)
    return parser.cards


def _booking_item_sort_key(item: RawItem) -> tuple[float, int]:
    rating_match = re.search(r"rating ([0-9]+(?:\.[0-9]+)?)/10", item.title)
    price_match = re.search(r"(\d+) RUB/night", item.title)
    rating = float(rating_match.group(1)) if rating_match else 0.0
    price = int(price_match.group(1)) if price_match else 10**9
    return (-rating, price)


class _BookingHotelCardParser(HTMLParser):
    FIELD_TEST_IDS = {
        "title": "title",
        "price-and-discounted-price": "price",
        "review-score": "rating",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, Any]] = []
        self._in_card = False
        self._card_depth = 0
        self._card: dict[str, Any] = {}
        self._field: str | None = None
        self._field_depth = 0
        self._field_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        test_id = attr_map.get("data-testid")
        if not self._in_card and test_id == "property-card":
            self._in_card = True
            self._card_depth = 1
            self._card = {}
            return

        if not self._in_card:
            return

        self._card_depth += 1
        if test_id == "title-link" and attr_map.get("href"):
            self._card["url"] = urljoin("https://www.booking.com", attr_map["href"])
        if test_id in self.FIELD_TEST_IDS:
            self._field = self.FIELD_TEST_IDS[test_id]
            self._field_depth = self._card_depth
            self._field_text = []

    def handle_data(self, data: str) -> None:
        if self._field:
            text = data.strip()
            if text:
                self._field_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_card:
            return

        if self._field and self._card_depth == self._field_depth:
            text = " ".join(self._field_text)
            if self._field == "price":
                self._card["price_rub"] = _parse_booking_price_rub(text)
            elif self._field == "rating":
                self._card["rating"] = _parse_booking_rating(text)
            else:
                self._card[self._field] = text
            self._field = None
            self._field_text = []

        self._card_depth -= 1
        if self._card_depth == 0:
            if self._card.get("title"):
                self.cards.append(self._card)
            self._in_card = False
            self._card = {}


def _parse_booking_price_rub(text: str) -> int | None:
    if not re.search(r"\bRUB\b|₽|руб", text, re.IGNORECASE):
        return None
    match = re.search(r"(\d[\d\s,.]*)", text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def _parse_booking_rating(text: str) -> float | None:
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)", text)
    if not match:
        return None
    rating = float(match.group(1).replace(",", "."))
    return rating if 0 <= rating <= 10 else None
