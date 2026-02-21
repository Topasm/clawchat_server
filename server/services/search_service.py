from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.search import SearchHit

ALL_TYPES = ["messages", "todos", "events", "memos"]


async def search(
    db: AsyncSession,
    query: str,
    types: list[str] | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[SearchHit], int]:
    """Full-text search across messages, todos, events, and memos."""
    enabled = types or ALL_TYPES
    hits: list[SearchHit] = []

    # Sanitize query for FTS5: wrap each token in double quotes to treat as literals
    fts_query = " ".join(f'"{token}"' for token in query.split() if token)
    if not fts_query:
        return [], 0

    if "messages" in enabled:
        rows = (await db.execute(
            text("""
                SELECT f.id, f.content, bm25(messages_fts) AS rank, m.created_at
                FROM messages_fts f
                JOIN messages m ON m.id = f.id
                WHERE messages_fts MATCH :q
                ORDER BY rank
            """),
            {"q": fts_query},
        )).fetchall()
        for r in rows:
            preview = r.content[:200] if r.content else ""
            hits.append(SearchHit(
                type="message",
                id=r.id,
                title=None,
                preview=preview,
                rank=r.rank,
                created_at=_parse_dt(r.created_at),
            ))

    if "todos" in enabled:
        rows = (await db.execute(
            text("""
                SELECT f.id, f.title, f.description, bm25(todos_fts) AS rank, t.created_at
                FROM todos_fts f
                JOIN todos t ON t.id = f.id
                WHERE todos_fts MATCH :q
                ORDER BY rank
            """),
            {"q": fts_query},
        )).fetchall()
        for r in rows:
            preview = r.description[:200] if r.description else r.title
            hits.append(SearchHit(
                type="todo",
                id=r.id,
                title=r.title,
                preview=preview,
                rank=r.rank,
                created_at=_parse_dt(r.created_at),
            ))

    if "events" in enabled:
        rows = (await db.execute(
            text("""
                SELECT f.id, f.title, f.description, f.location, bm25(events_fts) AS rank, e.created_at
                FROM events_fts f
                JOIN events e ON e.id = f.id
                WHERE events_fts MATCH :q
                ORDER BY rank
            """),
            {"q": fts_query},
        )).fetchall()
        for r in rows:
            parts = [p for p in [r.description, r.location] if p]
            preview = " | ".join(parts)[:200] if parts else r.title
            hits.append(SearchHit(
                type="event",
                id=r.id,
                title=r.title,
                preview=preview,
                rank=r.rank,
                created_at=_parse_dt(r.created_at),
            ))

    if "memos" in enabled:
        rows = (await db.execute(
            text("""
                SELECT f.id, f.title, f.content, bm25(memos_fts) AS rank, m.created_at
                FROM memos_fts f
                JOIN memos m ON m.id = f.id
                WHERE memos_fts MATCH :q
                ORDER BY rank
            """),
            {"q": fts_query},
        )).fetchall()
        for r in rows:
            preview = r.content[:200] if r.content else r.title
            hits.append(SearchHit(
                type="memo",
                id=r.id,
                title=r.title,
                preview=preview,
                rank=r.rank,
                created_at=_parse_dt(r.created_at),
            ))

    # Sort all hits by bm25 rank (lower = more relevant)
    hits.sort(key=lambda h: h.rank)
    total = len(hits)

    # Paginate
    start = (page - 1) * limit
    return hits[start : start + limit], total


def _parse_dt(val) -> datetime:
    """Parse a datetime value that may come back as string from raw SQL."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return datetime.min
