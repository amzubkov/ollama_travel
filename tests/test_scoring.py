from travel_deals_agent.models import RawItem
from travel_deals_agent.scoring import (
    heuristic_score,
    is_cruise_discount_candidate,
    is_hotel_discount_candidate,
    is_relevant_item,
)
from travel_deals_agent.sources import Watchlist


def test_high_value_terms_raise_score() -> None:
    item = RawItem(
        source="test",
        title="Mistake fare to New Zealand with free flight promo",
        url="https://example.com/deal",
    )
    score = heuristic_score(item, Watchlist(keywords=["new zealand"], destinations=["AKL"]))
    assert score >= 70


def test_region_filter_excludes_america_without_interest_match() -> None:
    item = RawItem(
        source="test",
        title="United: San Francisco to Hawaii from $276",
        url="https://example.com/us-deal",
    )
    watchlist = Watchlist(
        include_keywords=["georgia", "armenia", "cyprus", "turkey", "russia", "europe"],
        exclude_keywords=["san francisco", "hawaii", "united states"],
    )
    assert not is_relevant_item(item, watchlist)


def test_region_filter_keeps_target_origin_to_any_destination() -> None:
    item = RawItem(
        source="test",
        title="Cheap flights from Tbilisi to New York",
        url="https://example.com/tbilisi-new-york",
    )
    watchlist = Watchlist(
        origins=["TBS"],
        include_keywords=["tbilisi"],
        exclude_keywords=["new york", "hawaii"],
    )
    assert is_relevant_item(item, watchlist)


def test_region_filter_keeps_added_departure_points() -> None:
    item = RawItem(
        source="test",
        title="Business class deal from Dubai to Tokyo",
        url="https://example.com/dubai-tokyo",
    )
    watchlist = Watchlist(
        origins=["DXB", "AUH", "KUF", "ULV", "URA"],
        include_keywords=["dubai", "abu dhabi", "samara", "ulyanovsk", "uralsk"],
        exclude_keywords=["tokyo"],
    )
    assert is_relevant_item(item, watchlist)


def test_hotel_discount_candidate_keeps_target_regions() -> None:
    item = RawItem(
        source="test",
        title="Istanbul luxury hotel 55% off for winter stays",
        url="https://example.com/istanbul-hotel",
    )
    watchlist = Watchlist(
        hotel_keywords=["hotel"],
        hotel_region_keywords=["istanbul", "turkey", "europe", "russia", "georgia"],
        min_hotel_discount_percent=50,
    )
    assert is_hotel_discount_candidate(item, watchlist)
    assert is_relevant_item(item, watchlist)


def test_hotel_discount_candidate_rejects_out_of_scope_regions() -> None:
    item = RawItem(
        source="test",
        title="Mexico beach resort 70% off",
        url="https://example.com/mexico-resort",
    )
    watchlist = Watchlist(
        hotel_keywords=["hotel", "resort"],
        hotel_region_keywords=["europe", "russia", "georgia", "turkey"],
        min_hotel_discount_percent=50,
    )
    assert not is_hotel_discount_candidate(item, watchlist)


def test_cruise_discount_candidate_keeps_target_regions() -> None:
    item = RawItem(
        source="test",
        title="Mediterranean cruise cabins 60% off from Istanbul",
        url="https://example.com/med-cruise",
    )
    watchlist = Watchlist(
        cruise_keywords=["cruise", "cabin"],
        cruise_region_keywords=["mediterranean", "istanbul", "turkey", "europe"],
        min_cruise_discount_percent=50,
    )
    assert is_cruise_discount_candidate(item, watchlist)
    assert is_relevant_item(item, watchlist)


def test_cruise_discount_candidate_rejects_out_of_scope_regions() -> None:
    item = RawItem(
        source="test",
        title="Caribbean cruise cabins 70% off",
        url="https://example.com/caribbean-cruise",
    )
    watchlist = Watchlist(
        cruise_keywords=["cruise", "cabin"],
        cruise_region_keywords=["mediterranean", "europe", "turkey", "georgia", "russia"],
        min_cruise_discount_percent=50,
    )
    assert not is_cruise_discount_candidate(item, watchlist)
