from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from travel_deals_agent.collectors import (
    collect_aviasales_calendar,
    collect_aviasales_exact_trip,
    collect_rss,
    collect_tracked_hotel_stay,
)
from travel_deals_agent.llm import analyze_item
from travel_deals_agent.models import DealAnalysis
from travel_deals_agent.notifiers import format_alert, format_scan_summary, send_telegram
from travel_deals_agent.scoring import classify_item, heuristic_score, is_relevant_item
from travel_deals_agent.settings import get_settings
from travel_deals_agent.sources import load_sources
from travel_deals_agent.storage import (
    connect,
    deal_exists,
    finish_scan_run,
    get_deal_stats,
    list_deals,
    list_scan_runs,
    list_scan_source_runs,
    record_scan_source_run,
    start_scan_run,
    upsert_deal,
)

console = Console()


@click.group()
def main() -> None:
    pass


@main.command()
@click.option("--sources", "sources_path", default="config/sources.json", type=click.Path(path_type=Path))
@click.option("--no-llm", is_flag=True, help="Use heuristic scoring only.")
@click.option("--alert/--no-alert", default=True, help="Send Telegram alerts when configured.")
def scan(sources_path: Path, no_llm: bool, alert: bool) -> None:
    settings = get_settings()
    source_config = load_sources(sources_path)
    conn = connect(settings.database_path)
    sources_count = (
        len(source_config.rss)
        + len(source_config.aviasales_calendar)
        + len(source_config.aviasales_exact_trips)
        + len(source_config.tracked_hotel_stays)
    )
    scan_run_id = start_scan_run(conn, sources_count, no_llm)

    total = 0
    filtered = 0
    skipped = 0
    inserted = 0
    alerted = 0
    errors = 0
    category_stats = {
        "flight": {"candidates": 0, "inserted": 0, "alerted": 0},
        "hotel": {"candidates": 0, "inserted": 0, "alerted": 0},
        "cruise": {"candidates": 0, "inserted": 0, "alerted": 0},
    }

    def process_items(source_name: str, source_url: str, items: list) -> tuple[int, int, int, int, int]:
        nonlocal total, filtered, skipped, inserted, alerted
        source_skipped = 0
        source_filtered = 0
        source_inserted = 0
        source_alerted = 0

        for item in items:
            total += 1
            if not is_relevant_item(item, source_config.watchlist):
                filtered += 1
                source_filtered += 1
                continue

            item_type = classify_item(item, source_config.watchlist)
            category_stats[item_type]["candidates"] += 1

            if deal_exists(conn, str(item.url)):
                skipped += 1
                source_skipped += 1
                continue

            base_score = heuristic_score(item, source_config.watchlist)
            console.print(f"Analyzing {base_score}/100 candidate: {item.title[:90]}")
            if no_llm:
                analysis = DealAnalysis(
                    category="unknown",
                    score=base_score,
                    summary=item.title,
                    is_alert_worthy=base_score >= settings.min_score_to_alert,
                )
            else:
                try:
                    analysis = analyze_item(item, base_score, settings)
                except Exception as exc:
                    console.print(f"[yellow]LLM failed[/yellow] {item.title}: {exc}")
                    analysis = DealAnalysis(
                        category="unknown",
                        score=base_score,
                        summary=item.title,
                        is_alert_worthy=base_score >= settings.min_score_to_alert,
                        risks=[f"LLM analysis failed: {exc}"],
                    )

            if upsert_deal(conn, item, analysis):
                inserted += 1
                category_stats[item_type]["inserted"] += 1
                source_inserted += 1
                if alert and analysis.is_alert_worthy:
                    text = format_alert(item, analysis)
                    if send_telegram(settings, text):
                        alerted += 1
                        category_stats[item_type]["alerted"] += 1
                        source_alerted += 1
                    else:
                        console.print(f"[cyan]Alert candidate[/cyan] {analysis.score}/100 {item.title}")

        record_scan_source_run(
            conn,
            scan_run_id,
            source=source_name,
            url=source_url,
            status="ok",
            fetched_items=len(items),
            filtered_items=source_filtered,
            skipped_items=source_skipped,
            inserted_items=source_inserted,
            alerted_items=source_alerted,
        )
        return len(items), source_filtered, source_skipped, source_inserted, source_alerted

    for source in source_config.rss:
        console.print(f"[bold]Collecting[/bold] {source.name}")
        try:
            items = collect_rss(source)
        except Exception as exc:
            errors += 1
            console.print(f"[red]Failed[/red] {source.name}: {exc}")
            record_scan_source_run(
                conn,
                scan_run_id,
                source=source.name,
                url=str(source.url),
                status="failed",
                error=str(exc),
            )
            continue
        process_items(source.name, str(source.url), items)

    for source in source_config.aviasales_calendar:
        console.print(f"[bold]Collecting[/bold] {source.name}")
        try:
            items = collect_aviasales_calendar(source)
        except Exception as exc:
            errors += 1
            console.print(f"[red]Failed[/red] {source.name}: {exc}")
            record_scan_source_run(
                conn,
                scan_run_id,
                source=source.name,
                url="https://explore-api.aviasales.ru/api/v6/calendar.json",
                status="failed",
                error=str(exc),
            )
            continue
        process_items(source.name, "https://explore-api.aviasales.ru/api/v6/calendar.json", items)

    for source in source_config.aviasales_exact_trips:
        console.print(f"[bold]Collecting[/bold] {source.name}")
        try:
            items = collect_aviasales_exact_trip(source)
        except Exception as exc:
            errors += 1
            console.print(f"[red]Failed[/red] {source.name}: {exc}")
            record_scan_source_run(
                conn,
                scan_run_id,
                source=source.name,
                url="https://explore-api.aviasales.ru/api/v6/calendar.json",
                status="failed",
                error=str(exc),
            )
            continue
        process_items(source.name, "https://explore-api.aviasales.ru/api/v6/calendar.json", items)

    for source in source_config.tracked_hotel_stays:
        console.print(f"[bold]Collecting[/bold] {source.name}")
        try:
            items = collect_tracked_hotel_stay(source)
        except Exception as exc:
            errors += 1
            console.print(f"[red]Failed[/red] {source.name}: {exc}")
            record_scan_source_run(
                conn,
                scan_run_id,
                source=source.name,
                url="https://www.aviasales.ru/hotels/search",
                status="failed",
                error=str(exc),
            )
            continue
        process_items(source.name, "https://www.aviasales.ru/hotels/search", items)

    finish_scan_run(
        conn,
        scan_run_id,
        total_items=total,
        filtered_items=filtered,
        skipped_items=skipped,
        inserted_items=inserted,
        alerted_items=alerted,
        error_count=errors,
    )
    console.print(
        f"Scanned {total} items, filtered {filtered}, skipped {skipped}, inserted {inserted}, alerted {alerted}."
    )
    if alert and settings.send_scan_summary:
        summary = format_scan_summary(
            total=total,
            filtered=filtered,
            skipped=skipped,
            inserted=inserted,
            alerted=alerted,
            errors=errors,
            category_stats=category_stats,
        )
        if not send_telegram(settings, summary):
            console.print("[cyan]Scan summary[/cyan]\n" + summary)


@main.command("list")
@click.option("--limit", default=20, type=int)
def list_command(limit: int) -> None:
    settings = get_settings()
    conn = connect(settings.database_path)
    deals = list_deals(conn, limit=limit)

    table = Table(title="Stored Travel Deals")
    table.add_column("Score", justify="right")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("URL")

    for deal in deals:
        table.add_row(str(deal.score), deal.source, deal.title, deal.url)

    console.print(table)


@main.command()
@click.option("--sources", "sources_path", default="config/sources.json", type=click.Path(path_type=Path))
def sources(sources_path: Path) -> None:
    source_config = load_sources(sources_path)

    source_table = Table(title="Configured RSS Sources")
    source_table.add_column("#", justify="right")
    source_table.add_column("Name")
    source_table.add_column("URL")
    for index, source in enumerate(source_config.rss, start=1):
        source_table.add_row(str(index), source.name, str(source.url))
    console.print(source_table)

    aviasales_table = Table(title="Configured Aviasales Calendar Sources")
    aviasales_table.add_column("#", justify="right")
    aviasales_table.add_column("Name")
    aviasales_table.add_column("Origins")
    aviasales_table.add_column("Destinations")
    aviasales_table.add_column("Max RUB", justify="right")
    for index, source in enumerate(source_config.aviasales_calendar, start=1):
        aviasales_table.add_row(
            str(index),
            source.name,
            ", ".join(source.origins),
            ", ".join(source.destinations),
            str(source.max_price_rub or "-"),
        )
    console.print(aviasales_table)

    exact_table = Table(title="Configured Aviasales Exact Trips")
    exact_table.add_column("#", justify="right")
    exact_table.add_column("Name")
    exact_table.add_column("Route")
    exact_table.add_column("Dates")
    exact_table.add_column("Max RUB", justify="right")
    for index, source in enumerate(source_config.aviasales_exact_trips, start=1):
        dates = source.depart_date if source.return_date is None else f"{source.depart_date} to {source.return_date}"
        exact_table.add_row(
            str(index),
            source.name,
            f"{source.origin}-{source.destination}",
            dates,
            str(source.max_price_rub or "-"),
        )
    console.print(exact_table)

    hotel_table = Table(title="Configured Tracked Hotel Stays")
    hotel_table.add_column("#", justify="right")
    hotel_table.add_column("Name")
    hotel_table.add_column("City")
    hotel_table.add_column("Dates")
    hotel_table.add_column("Adults", justify="right")
    for index, source in enumerate(source_config.tracked_hotel_stays, start=1):
        hotel_table.add_row(
            str(index),
            source.name,
            source.city,
            f"{source.checkin} to {source.checkout}",
            str(source.adults),
        )
    console.print(hotel_table)

    watch_table = Table(title="Watchlist")
    watch_table.add_column("Type")
    watch_table.add_column("Values")
    watch_table.add_row("Origins", ", ".join(source_config.watchlist.origins))
    watch_table.add_row("Destinations", ", ".join(source_config.watchlist.destinations))
    watch_table.add_row("Keywords", ", ".join(source_config.watchlist.keywords))
    console.print(watch_table)


@main.command()
@click.option("--limit", default=10, type=int)
@click.option("--run-id", type=int, default=None)
def runs(limit: int, run_id: int | None) -> None:
    settings = get_settings()
    conn = connect(settings.database_path)

    if run_id is None:
        table = Table(title="Recent Scan Runs")
        table.add_column("ID", justify="right")
        table.add_column("Started")
        table.add_column("Finished")
        table.add_column("Sources", justify="right")
        table.add_column("Items", justify="right")
        table.add_column("Filtered", justify="right")
        table.add_column("Skipped", justify="right")
        table.add_column("Inserted", justify="right")
        table.add_column("Alerts", justify="right")
        table.add_column("Errors", justify="right")
        table.add_column("LLM")
        for row in list_scan_runs(conn, limit=limit):
            table.add_row(
                str(row["id"]),
                row["started_at"],
                row["finished_at"] or "-",
                str(row["sources_count"]),
                str(row["total_items"]),
                str(row["filtered_items"]),
                str(row["skipped_items"]),
                str(row["inserted_items"]),
                str(row["alerted_items"]),
                str(row["error_count"]),
                "off" if row["no_llm"] else "on",
            )
        console.print(table)
        return

    table = Table(title=f"Scan Run {run_id} Sources")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Fetched", justify="right")
    table.add_column("Filtered", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Inserted", justify="right")
    table.add_column("Alerts", justify="right")
    table.add_column("Error")
    for row in list_scan_source_runs(conn, run_id):
        table.add_row(
            row["source"],
            row["status"],
            str(row["fetched_items"]),
            str(row["filtered_items"]),
            str(row["skipped_items"]),
            str(row["inserted_items"]),
            str(row["alerted_items"]),
            row["error"] or "",
        )
    console.print(table)


@main.command()
@click.option("--sources", "sources_path", default="config/sources.json", type=click.Path(path_type=Path))
def status(sources_path: Path) -> None:
    settings = get_settings()
    source_config = load_sources(sources_path)
    conn = connect(settings.database_path)
    stats = get_deal_stats(conn)

    summary = Table(title="Travel Deals Agent Status")
    summary.add_column("Setting")
    summary.add_column("Value")
    summary.add_row("Ollama model", settings.ollama_model)
    summary.add_row("Ollama API key", "set" if settings.ollama_api_key else "missing")
    summary.add_row("Telegram", "set" if settings.telegram_bot_token and settings.telegram_chat_id else "missing")
    summary.add_row("Alert threshold", str(settings.min_score_to_alert))
    summary.add_row("Database", str(settings.database_path))
    summary.add_row("RSS sources", str(len(source_config.rss)))
    summary.add_row("Aviasales calendar sources", str(len(source_config.aviasales_calendar)))
    summary.add_row("Aviasales exact trip sources", str(len(source_config.aviasales_exact_trips)))
    summary.add_row("Tracked hotel stay sources", str(len(source_config.tracked_hotel_stays)))
    summary.add_row("Origins watched", str(len(source_config.watchlist.origins)))
    summary.add_row("Destinations watched", str(len(source_config.watchlist.destinations)))
    summary.add_row("Keywords watched", str(len(source_config.watchlist.keywords)))
    summary.add_row("Deals stored", str(stats["total"]))
    summary.add_row("Inserted last 24h", str(stats["inserted_24h"]))
    summary.add_row("Max score", str(stats["max_score"]))
    summary.add_row("Deals score >= 50", str(stats["score_50_plus"]))
    summary.add_row("Deals score >= 70", str(stats["score_70_plus"]))
    summary.add_row("Last inserted", stats["last_inserted_at"] or "never")
    console.print(summary)

    source_table = Table(title="Stored Deals by Source")
    source_table.add_column("Source")
    source_table.add_column("Deals", justify="right")
    source_table.add_column("Max score", justify="right")
    for row in stats["by_source"]:
        source_table.add_row(row["source"], str(row["count"]), str(row["max_score"]))
    console.print(source_table)


if __name__ == "__main__":
    main()
