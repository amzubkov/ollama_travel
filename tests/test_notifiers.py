from travel_deals_agent.notifiers import format_scan_summary


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
