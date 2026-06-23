import httpx

from travel_deals_agent.models import DealAnalysis, RawItem
from travel_deals_agent.settings import Settings


def format_alert(item: RawItem, analysis: DealAnalysis) -> str:
    risks = "\n".join(f"- {risk}" for risk in analysis.risks[:3]) or "- none identified"
    checks = "\n".join(f"- {check}" for check in analysis.next_checks[:3]) or "- re-check availability"
    return (
        f"{analysis.summary}\n\n"
        f"Score: {analysis.score}/100\n"
        f"Source: {item.source}\n"
        f"URL: {item.url}\n\n"
        f"Risks:\n{risks}\n\n"
        f"Next checks:\n{checks}"
    )


def send_telegram(settings: Settings, text: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False

    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": settings.telegram_chat_id, "text": text, "disable_web_page_preview": False},
        timeout=20,
    )
    response.raise_for_status()
    return True
