import httpx

from travel_deals_agent.models import DealAnalysis, RawItem
from travel_deals_agent.settings import Settings
from travel_deals_agent.sources import SourceConfig


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


def format_telegram_help(source_config: SourceConfig, settings: Settings) -> str:
    lines = [
        "Travel Deals Agent help",
        "",
        "Schedule:",
        "- fisherocean cron runs at 00:00, 04:00, then every 2 hours from 08:00 to 22:00 Asia/Tbilisi",
        f"- Telegram alert threshold: {settings.min_score_to_alert}/100",
        "- Scan summaries are controlled by SEND_SCAN_SUMMARY",
        "",
        "Manual commands on fisherocean:",
        "- cd /home/fisherocean/travel-deals-agent",
        "- docker compose run --rm agent scan",
        "- docker compose run --rm agent status",
        "- docker compose run --rm agent runs --limit 5",
        "- docker compose run --rm agent list --limit 20",
        "",
        "Tracked exact flights:",
    ]
    if source_config.aviasales_exact_trips:
        for source in source_config.aviasales_exact_trips:
            dates = source.depart_date if source.return_date is None else f"{source.depart_date} to {source.return_date}"
            route = f"{source.origin_name or source.origin} ({source.origin}) -> "
            route += f"{source.destination_name or source.destination} ({source.destination})"
            max_price = f", max {source.max_price_rub} RUB" if source.max_price_rub else ""
            lines.append(f"- {route}, {dates}{max_price}")
    else:
        lines.append("- none")

    lines.extend(["", "Tracked hotel stays:"])
    if source_config.tracked_hotel_stays:
        for source in source_config.tracked_hotel_stays:
            lines.append(f"- {source.city}, {source.checkin} to {source.checkout}, adults {source.adults}")
    else:
        lines.append("- none")

    lines.extend(["", "Broad sources:"])
    lines.append(f"- RSS feeds: {len(source_config.rss)}")
    lines.append(f"- Aviasales calendar sources: {len(source_config.aviasales_calendar)}")
    for source in source_config.aviasales_calendar:
        origins = ", ".join(source.origins)
        destination_count = len(source.destinations)
        max_price = f", max {source.max_price_rub} RUB" if source.max_price_rub else ""
        lines.append(f"- {source.name}: from {origins}, {destination_count} destinations{max_price}")

    lines.extend(
        [
            "",
            "Notes:",
            "- This Telegram bot is outbound-only right now; commands above are run over SSH.",
            "- Hotel stay tracking currently sends a dated search link, not extracted hotel prices.",
        ]
    )
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
