from pathlib import Path
import json
import sqlite3
from typing import Any

from travel_deals_agent.models import DealAnalysis, RawItem, StoredDeal


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL UNIQUE,
          summary TEXT NOT NULL,
          published_at TEXT,
          score INTEGER NOT NULL DEFAULT 0,
          analysis_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          finished_at TEXT,
          sources_count INTEGER NOT NULL DEFAULT 0,
          total_items INTEGER NOT NULL DEFAULT 0,
          filtered_items INTEGER NOT NULL DEFAULT 0,
          skipped_items INTEGER NOT NULL DEFAULT 0,
          inserted_items INTEGER NOT NULL DEFAULT 0,
          alerted_items INTEGER NOT NULL DEFAULT 0,
          error_count INTEGER NOT NULL DEFAULT 0,
          no_llm INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_source_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          scan_run_id INTEGER NOT NULL,
          source TEXT NOT NULL,
          url TEXT NOT NULL,
          status TEXT NOT NULL,
          fetched_items INTEGER NOT NULL DEFAULT 0,
          filtered_items INTEGER NOT NULL DEFAULT 0,
          skipped_items INTEGER NOT NULL DEFAULT 0,
          inserted_items INTEGER NOT NULL DEFAULT 0,
          alerted_items INTEGER NOT NULL DEFAULT 0,
          error TEXT,
          started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          finished_at TEXT,
          FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id)
        )
        """
    )
    ensure_column(conn, "scan_runs", "filtered_items", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "scan_source_runs", "filtered_items", "INTEGER NOT NULL DEFAULT 0")
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def start_scan_run(conn: sqlite3.Connection, sources_count: int, no_llm: bool) -> int:
    cursor = conn.execute(
        "INSERT INTO scan_runs (sources_count, no_llm) VALUES (?, ?)",
        (sources_count, int(no_llm)),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_scan_run(
    conn: sqlite3.Connection,
    scan_run_id: int,
    *,
    total_items: int,
    filtered_items: int,
    skipped_items: int,
    inserted_items: int,
    alerted_items: int,
    error_count: int,
) -> None:
    conn.execute(
        """
        UPDATE scan_runs
        SET finished_at = CURRENT_TIMESTAMP,
            total_items = ?,
            filtered_items = ?,
            skipped_items = ?,
            inserted_items = ?,
            alerted_items = ?,
            error_count = ?
        WHERE id = ?
        """,
        (total_items, filtered_items, skipped_items, inserted_items, alerted_items, error_count, scan_run_id),
    )
    conn.commit()


def record_scan_source_run(
    conn: sqlite3.Connection,
    scan_run_id: int,
    *,
    source: str,
    url: str,
    status: str,
    fetched_items: int = 0,
    filtered_items: int = 0,
    skipped_items: int = 0,
    inserted_items: int = 0,
    alerted_items: int = 0,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO scan_source_runs
          (scan_run_id, source, url, status, fetched_items, filtered_items, skipped_items, inserted_items, alerted_items, error, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            scan_run_id,
            source,
            url,
            status,
            fetched_items,
            filtered_items,
            skipped_items,
            inserted_items,
            alerted_items,
            error,
        ),
    )
    conn.commit()


def upsert_deal(conn: sqlite3.Connection, item: RawItem, analysis: DealAnalysis) -> bool:
    before = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO deals
          (source, title, url, summary, published_at, score, analysis_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.source,
            item.title,
            str(item.url),
            item.summary,
            item.published_at.isoformat() if item.published_at else None,
            analysis.score,
            analysis.model_dump_json(),
        ),
    )
    conn.commit()
    return conn.total_changes > before


def deal_exists(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM deals WHERE url = ? LIMIT 1", (url,)).fetchone()
    return row is not None


def get_deal_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          COALESCE(MAX(score), 0) AS max_score,
          MAX(created_at) AS last_inserted_at,
          SUM(CASE WHEN created_at >= datetime('now', '-24 hours') THEN 1 ELSE 0 END) AS inserted_24h,
          SUM(CASE WHEN score >= 70 THEN 1 ELSE 0 END) AS score_70_plus,
          SUM(CASE WHEN score >= 50 THEN 1 ELSE 0 END) AS score_50_plus
        FROM deals
        """
    ).fetchone()
    by_source = conn.execute(
        """
        SELECT source, COUNT(*) AS count, COALESCE(MAX(score), 0) AS max_score
        FROM deals
        GROUP BY source
        ORDER BY count DESC, source ASC
        """
    ).fetchall()
    return {
        "total": row["total"] or 0,
        "max_score": row["max_score"] or 0,
        "last_inserted_at": row["last_inserted_at"],
        "inserted_24h": row["inserted_24h"] or 0,
        "score_70_plus": row["score_70_plus"] or 0,
        "score_50_plus": row["score_50_plus"] or 0,
        "by_source": [dict(source=r["source"], count=r["count"], max_score=r["max_score"]) for r in by_source],
    }


def list_scan_runs(conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, started_at, finished_at, sources_count, total_items, filtered_items, skipped_items,
               inserted_items, alerted_items, error_count, no_llm
        FROM scan_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_scan_source_runs(conn: sqlite3.Connection, scan_run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source, url, status, fetched_items, filtered_items, skipped_items, inserted_items,
               alerted_items, error, started_at, finished_at
        FROM scan_source_runs
        WHERE scan_run_id = ?
        ORDER BY id ASC
        """,
        (scan_run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_deals(conn: sqlite3.Connection, limit: int = 20) -> list[StoredDeal]:
    rows = conn.execute(
        """
        SELECT id, source, title, url, summary, published_at, score, analysis_json, created_at
        FROM deals
        ORDER BY score DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        StoredDeal(
            id=row["id"],
            source=row["source"],
            title=row["title"],
            url=row["url"],
            summary=row["summary"],
            published_at=row["published_at"],
            score=row["score"],
            analysis=json.loads(row["analysis_json"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
