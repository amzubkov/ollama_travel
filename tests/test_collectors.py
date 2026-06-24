from travel_deals_agent.collectors import (
    _items_from_aviasales_calendar_response,
    _items_from_aviasales_exact_trip_response,
    collect_tracked_hotel_stay,
)
from travel_deals_agent.scoring import heuristic_score, is_relevant_item
from travel_deals_agent.sources import AviasalesCalendarSource, AviasalesExactTripSource, TrackedHotelStaySource, Watchlist


def test_aviasales_calendar_keeps_best_low_fare() -> None:
    source = AviasalesCalendarSource(
        name="Aviasales Calendar KUF Anywhere",
        max_price_rub=20_000,
    )
    item = _items_from_aviasales_calendar_response(
        source=source,
        origin="KUF",
        destination="IST",
        payload={
            "prices": [
                {"depart_date": "2026-07-10", "return_date": None, "price": 18_000, "state": "EXISTS"},
                {"depart_date": "2026-07-12", "return_date": None, "price": 12_000, "state": "EXISTS"},
            ]
        },
    )[0]

    assert "KUF to IST" in item.title
    assert "12000 RUB" in item.title
    assert str(item.url).endswith("/search/KUF1207IST1")


def test_aviasales_calendar_rejects_price_above_limit() -> None:
    source = AviasalesCalendarSource(max_price_rub=10_000)

    items = _items_from_aviasales_calendar_response(
        source=source,
        origin="KUF",
        destination="IST",
        payload={"prices": [{"depart_date": "2026-07-10", "price": 18_000, "state": "EXISTS"}]},
    )

    assert items == []


def test_aviasales_low_fare_is_relevant_and_alertable_by_heuristic() -> None:
    source = AviasalesCalendarSource(max_price_rub=20_000)
    item = _items_from_aviasales_calendar_response(
        source=source,
        origin="KUF",
        destination="IST",
        payload={"prices": [{"depart_date": "2026-07-10", "price": 12_000, "state": "EXISTS"}]},
    )[0]
    watchlist = Watchlist(origins=["KUF"], destinations=["WORLD"], include_keywords=["samara"])

    assert is_relevant_item(item, watchlist)
    assert heuristic_score(item, watchlist) >= 35


def test_aviasales_exact_trip_keeps_exact_dates() -> None:
    source = AviasalesExactTripSource(
        name="Tracked Flight MOW LED Jun 25-26",
        origin="MOW",
        destination="LED",
        origin_name="Moscow",
        destination_name="Saint Petersburg",
        depart_date="2026-06-25",
        return_date="2026-06-26",
        max_price_rub=20_000,
    )
    item = _items_from_aviasales_exact_trip_response(
        source=source,
        payload={
            "prices": [
                {"depart_date": "2026-06-25", "return_date": "2026-06-27", "price": 7_000, "state": "EXISTS"},
                {"depart_date": "2026-06-25", "return_date": "2026-06-26", "price": 6_613, "state": "EXISTS"},
            ]
        },
    )[0]
    watchlist = Watchlist(origins=["MOW"], include_keywords=["moscow", "saint petersburg"])

    assert "Moscow (MOW) to Saint Petersburg (LED)" in item.title
    assert "2026-06-25 to 2026-06-26" in item.title
    assert "6613 RUB" in item.title
    assert str(item.url).endswith("/search/MOW2506LED26061")
    assert is_relevant_item(item, watchlist)
    assert heuristic_score(item, watchlist) >= 60


def test_tracked_hotel_stay_builds_search_link_and_alertable_score() -> None:
    source = TrackedHotelStaySource(
        name="Tracked Hotel Saint Petersburg Jun 25-26",
        city="Saint Petersburg",
        location_id=3381,
        checkin="2026-06-25",
        checkout="2026-06-26",
        adults=2,
        max_price_rub=10_000,
        min_rating=9.0,
    )
    item = collect_tracked_hotel_stay(source)[0]
    watchlist = Watchlist(include_keywords=["saint petersburg"])

    assert "Tracked hotel stay: Saint Petersburg" in item.title
    assert "max 10000 RUB/night" in item.title
    assert "rating >= 9/10" in item.title
    assert "location_id=3381" in str(item.url)
    assert "checkin=2026-06-25" in str(item.url)
    assert "price_max=10000" in str(item.url)
    assert "rating_min=9" in str(item.url)
    assert is_relevant_item(item, watchlist)
    assert heuristic_score(item, watchlist) >= 60
