import re

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
    "low fare": 20,
}

HOTEL_TERMS = {
    "hotel",
    "resort",
    "stay",
    "stays",
    "night",
    "nights",
    "all-inclusive",
    "all inclusive",
    "hilton",
    "hyatt",
    "marriott",
    "ihg",
    "bonvoy",
}

CRUISE_TERMS = {
    "cruise",
    "cruises",
    "sailing",
    "sailings",
    "voyage",
    "voyages",
    "cabin",
    "cabins",
    "msc cruises",
    "royal caribbean",
    "costa cruises",
    "celestyal",
    "norwegian cruise line",
}


def extract_discount_percent(text: str) -> int | None:
    candidates: list[int] = []
    for match in re.finditer(r"(?<!\d)(\d{2})(?:\s?%|\s?percent)\s+(?:off|discount|cashback|back)", text):
        candidates.append(int(match.group(1)))
    for match in re.finditer(r"(?:save|saving|savings|discount|reduced|reduction)\D{0,20}(\d{2})(?:\s?%|\s?percent)", text):
        candidates.append(int(match.group(1)))
    if "half price" in text or "50% off" in text or "50 percent off" in text:
        candidates.append(50)
    return max(candidates) if candidates else None


def is_hotel_discount_candidate(item: RawItem, watchlist: Watchlist) -> bool:
    text = f"{item.title}\n{item.summary}".lower()
    hotel_terms = {*HOTEL_TERMS, *[term.lower() for term in watchlist.hotel_keywords]}
    has_hotel_term = any(term in text for term in hotel_terms)
    hotel_region_terms = [term.lower() for term in watchlist.hotel_region_keywords]
    has_hotel_region = not hotel_region_terms or any(term in text for term in hotel_region_terms)
    discount = extract_discount_percent(text)
    return (
        has_hotel_term
        and has_hotel_region
        and discount is not None
        and discount >= watchlist.min_hotel_discount_percent
    )


def is_cruise_discount_candidate(item: RawItem, watchlist: Watchlist) -> bool:
    text = f"{item.title}\n{item.summary}".lower()
    cruise_terms = {*CRUISE_TERMS, *[term.lower() for term in watchlist.cruise_keywords]}
    has_cruise_term = any(term in text for term in cruise_terms)
    cruise_region_terms = [term.lower() for term in watchlist.cruise_region_keywords]
    has_cruise_region = not cruise_region_terms or any(term in text for term in cruise_region_terms)
    discount = extract_discount_percent(text)
    return (
        has_cruise_term
        and has_cruise_region
        and discount is not None
        and discount >= watchlist.min_cruise_discount_percent
    )


def looks_like_hotel_item(item: RawItem, watchlist: Watchlist) -> bool:
    text = f"{item.title}\n{item.summary}".lower()
    hotel_terms = {*HOTEL_TERMS, *[term.lower() for term in watchlist.hotel_keywords]}
    return any(term in text for term in hotel_terms)


def looks_like_cruise_item(item: RawItem, watchlist: Watchlist) -> bool:
    text = f"{item.title}\n{item.summary}".lower()
    cruise_terms = {*CRUISE_TERMS, *[term.lower() for term in watchlist.cruise_keywords]}
    return any(term in text for term in cruise_terms)


def is_relevant_item(item: RawItem, watchlist: Watchlist) -> bool:
    if is_hotel_discount_candidate(item, watchlist) or is_cruise_discount_candidate(item, watchlist):
        return True

    if looks_like_hotel_item(item, watchlist) or looks_like_cruise_item(item, watchlist):
        return False

    text = f"{item.title}\n{item.summary}".lower()
    target_origin_terms = [
        *watchlist.origins,
        *watchlist.include_keywords,
    ]
    has_target_origin_match = any(term.lower() in text for term in target_origin_terms)

    if has_target_origin_match:
        return True

    return not any(term.lower() in text for term in watchlist.exclude_keywords)


def classify_item(item: RawItem, watchlist: Watchlist) -> str:
    if is_cruise_discount_candidate(item, watchlist):
        return "cruise"
    if is_hotel_discount_candidate(item, watchlist):
        return "hotel"
    return "flight"


def heuristic_score(item: RawItem, watchlist: Watchlist) -> int:
    text = f"{item.title}\n{item.summary}".lower()
    score = 10

    if is_hotel_discount_candidate(item, watchlist):
        score += 45
        discount = extract_discount_percent(text)
        if discount and discount >= 70:
            score += 10

    if is_cruise_discount_candidate(item, watchlist):
        score += 45
        discount = extract_discount_percent(text)
        if discount and discount >= 70:
            score += 10

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
