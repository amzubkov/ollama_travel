import json

from ollama import Client

from travel_deals_agent.models import DealAnalysis, RawItem
from travel_deals_agent.settings import Settings


SYSTEM_PROMPT = """You are a travel-deals analyst.
Extract real terms, hidden costs, risks, and next verification steps.
Be skeptical of clickbait. Return only valid JSON matching:
{
  "category": "flight_deal|event_bundle|promo|miles|unknown",
  "score": 0-100,
  "summary": "short human alert",
  "extracted_terms": ["..."],
  "risks": ["..."],
  "next_checks": ["..."],
  "is_alert_worthy": true|false
}
"""


def analyze_item(item: RawItem, base_score: int, settings: Settings) -> DealAnalysis:
    if not settings.ollama_api_key:
        return DealAnalysis(
            category="unknown",
            score=base_score,
            summary=item.title,
            is_alert_worthy=base_score >= settings.min_score_to_alert,
            next_checks=["Set OLLAMA_API_KEY to enable GLM analysis."],
        )

    client = Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {settings.ollama_api_key}"},
    )
    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "source": item.source,
                        "title": item.title,
                        "url": str(item.url),
                        "summary": item.summary[:4000],
                        "heuristic_score": base_score,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        format="json",
        options={"temperature": 0.1},
    )
    content = response["message"]["content"]
    data = json.loads(content)
    data["score"] = max(int(data.get("score", 0)), base_score)
    data["is_alert_worthy"] = bool(data.get("is_alert_worthy")) or data["score"] >= settings.min_score_to_alert
    return DealAnalysis.model_validate(data)
