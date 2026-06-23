from travel_deals_agent.models import RawItem
from travel_deals_agent.scoring import heuristic_score
from travel_deals_agent.sources import Watchlist


def test_high_value_terms_raise_score() -> None:
    item = RawItem(
        source="test",
        title="Mistake fare to New Zealand with free flight promo",
        url="https://example.com/deal",
    )
    score = heuristic_score(item, Watchlist(keywords=["new zealand"], destinations=["AKL"]))
    assert score >= 70
