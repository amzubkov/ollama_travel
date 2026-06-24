from travel_deals_agent.collectors import _items_from_aviasales_calendar_response
from travel_deals_agent.scoring import heuristic_score, is_relevant_item
from travel_deals_agent.sources import AviasalesCalendarSource, Watchlist


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
