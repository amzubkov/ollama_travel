from datetime import datetime, timezone

import feedparser
import httpx

from travel_deals_agent.models import RawItem
from travel_deals_agent.sources import RssSource


def collect_rss(source: RssSource, timeout: float = 20.0) -> list[RawItem]:
    response = httpx.get(
        str(source.url),
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": "travel-deals-agent/0.1 (+https://localhost)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    response.raise_for_status()
    parsed = feedparser.parse(response.text)

    items: list[RawItem] = []
    for entry in parsed.entries[:30]:
        published = None
        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        url = getattr(entry, "link", None)
        title = getattr(entry, "title", "").strip()
        if not url or not title:
            continue

        items.append(
            RawItem(
                source=source.name,
                title=title,
                url=url,
                summary=getattr(entry, "summary", ""),
                published_at=published,
            )
        )
    return items
