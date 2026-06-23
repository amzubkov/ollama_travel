import json
import sqlite3
from typing import Any
from pathlib import Path

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
    return conn


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
