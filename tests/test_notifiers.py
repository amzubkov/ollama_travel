from travel_deals_agent.notifiers import format_scan_summary, format_telegram_help
from travel_deals_agent.settings import Settings
from travel_deals_agent.sources import AviasalesCalendarSource, AviasalesExactTripSource, SourceConfig, TrackedHotelStaySource


def test_format_scan_summary_includes_categories() -> None:
    text = format_scan_summary(
        total=100,
        filtered=40,
        skipped=60,
        inserted=0,
        alerted=0,
        errors=0,
        category_stats={
            "flight": {"candidates": 50, "inserted": 0, "alerted": 0},
            "hotel": {"candidates": 5, "inserted": 0, "alerted": 0},
            "cruise": {"candidates": 1, "inserted": 0, "alerted": 0},
        },
    )
    assert "Flights: candidates 50" in text
    assert "Hotels: candidates 5" in text
    assert "Cruises: candidates 1" in text
    assert "Nothing new" in text


def test_format_telegram_help_includes_tracked_items() -> None:
    text = format_telegram_help(
        SourceConfig(
            rss=[],
            aviasales_calendar=[
                AviasalesCalendarSource(
                    name="Aviasales Calendar KUF Anywhere",
                    origins=["KUF"],
                    destinations=["MOW", "LED"],
                    max_price_rub=20_000,
                )
            ],
            aviasales_exact_trips=[
                AviasalesExactTripSource(
                    name="Tracked Flight MOW LED Jun 25-26",
                    origin="MOW",
                    destination="LED",
                    origin_name="Moscow",
                    destination_name="Saint Petersburg",
                    depart_date="2026-06-25",
                    return_date="2026-06-26",
                    max_price_rub=20_000,
                )
            ],
            tracked_hotel_stays=[
                TrackedHotelStaySource(
                    name="Tracked Hotel Saint Petersburg Jun 25-26",
                    city="Saint Petersburg",
                    location_id=3381,
                    checkin="2026-06-25",
                    checkout="2026-06-26",
                    adults=2,
                    max_price_rub=10_000,
                    min_rating=9.0,
                )
            ],
        ),
        Settings(min_score_to_alert=60),
    )

    assert "Travel Deals Agent help" in text
    assert "Moscow (MOW) -> Saint Petersburg (LED)" in text
    assert "Saint Petersburg, 2026-06-25 to 2026-06-26, adults 2, max 10000 RUB/night, rating >= 9/10" in text
    assert "Aviasales Calendar KUF Anywhere: from KUF, 2 destinations" in text
