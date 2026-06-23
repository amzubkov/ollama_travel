from travel_deals_agent.models import RawItem
from travel_deals_agent.sources import Watchlist


HIGH_VALUE_TERMS = {
    "mistake fare": 30,
    "error fare": 30,
    "free flight": 35,
    "companion pass": 25,
    "promo code": 15,
    "business class": 15,
    "new zealand": 15,
    "football": 10,
    "match ticket": 20,
}


def heuristic_score(item: RawItem, watchlist: Watchlist) -> int:
    text = f"{item.title}\n{item.summary}".lower()
    score = 10

    for term, points in HIGH_VALUE_TERMS.items():
        if term in text:
            score += points

    for keyword in watchlist.keywords:
        if keyword.lower() in text:
            score += 10

    for code in [*watchlist.origins, *watchlist.destinations]:
        if code.lower() in text:
            score += 5

    return min(score, 100)
