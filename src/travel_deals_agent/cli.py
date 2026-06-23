from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from travel_deals_agent.collectors import collect_rss
from travel_deals_agent.llm import analyze_item
from travel_deals_agent.models import DealAnalysis
from travel_deals_agent.notifiers import format_alert, send_telegram
from travel_deals_agent.scoring import heuristic_score
from travel_deals_agent.settings import get_settings
from travel_deals_agent.sources import load_sources
from travel_deals_agent.storage import connect, deal_exists, get_deal_stats, list_deals, upsert_deal

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

    total = 0
    skipped = 0
    inserted = 0
    alerted = 0

    for source in source_config.rss:
        console.print(f"[bold]Collecting[/bold] {source.name}")
        try:
            items = collect_rss(source)
        except Exception as exc:
            console.print(f"[red]Failed[/red] {source.name}: {exc}")
            continue

        for item in items:
            total += 1
            if deal_exists(conn, str(item.url)):
                skipped += 1
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
                if alert and analysis.is_alert_worthy:
                    text = format_alert(item, analysis)
                    if send_telegram(settings, text):
                        alerted += 1
                    else:
                        console.print(f"[cyan]Alert candidate[/cyan] {analysis.score}/100 {item.title}")

    console.print(f"Scanned {total} items, skipped {skipped}, inserted {inserted}, alerted {alerted}.")


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
