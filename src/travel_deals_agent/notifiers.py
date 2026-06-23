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


def format_scan_summary(
    *,
    total: int,
    filtered: int,
    skipped: int,
    inserted: int,
    alerted: int,
    errors: int,
    category_stats: dict[str, dict[str, int]],
) -> str:
    lines = [
        "Travel Deals Agent: scan complete",
        "",
        f"Total viewed: {total}",
        f"Filtered out: {filtered}",
        f"Already known: {skipped}",
        f"New saved: {inserted}",
        f"Alerts sent: {alerted}",
        f"Source errors: {errors}",
        "",
        "By type:",
    ]
    labels = {
        "flight": "Flights",
        "hotel": "Hotels",
        "cruise": "Cruises",
    }
    for key in ("flight", "hotel", "cruise"):
        stats = category_stats.get(key, {})
        lines.append(
            f"- {labels[key]}: candidates {stats.get('candidates', 0)}, "
            f"new {stats.get('inserted', 0)}, alerts {stats.get('alerted', 0)}"
        )
    if inserted == 0 and alerted == 0:
        lines.append("")
        lines.append("Nothing new matched the alert threshold this run.")
    return "\n".join(lines)


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
