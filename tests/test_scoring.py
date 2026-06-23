from travel_deals_agent.models import RawItem
from travel_deals_agent.scoring import heuristic_score, is_relevant_item
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


def test_region_filter_keeps_target_region() -> None:
    item = RawItem(
        source="test",
        title="Cheap flights from Tbilisi to Milan",
        url="https://example.com/tbilisi-milan",
    )
    watchlist = Watchlist(
        origins=["TBS"],
        include_keywords=["tbilisi", "milan", "europe"],
        exclude_keywords=["hawaii"],
    )
    assert is_relevant_item(item, watchlist)
