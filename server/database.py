import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ---------------------------------------------------------------------------
# FTS5 setup: individual DDL statements (triggers contain nested semicolons
# so we store them as a list rather than splitting on ";")
# ---------------------------------------------------------------------------

_FTS5_VIRTUAL_TABLES = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(id UNINDEXED, content)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS todos_fts USING fts5(id UNINDEXED, title, description)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(id UNINDEXED, title, description, location)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS memos_fts USING fts5(id UNINDEXED, title, content)",
]

_FTS5_TRIGGERS = [
    # -- Messages triggers
    """CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(id, content) VALUES (new.id, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
        DELETE FROM messages_fts WHERE id = old.id;
        INSERT INTO messages_fts(id, content) VALUES (new.id, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
        DELETE FROM messages_fts WHERE id = old.id;
    END""",
    # -- Todos triggers
    """CREATE TRIGGER IF NOT EXISTS todos_ai AFTER INSERT ON todos BEGIN
        INSERT INTO todos_fts(id, title, description)
        VALUES (new.id, new.title, COALESCE(new.description, ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS todos_au AFTER UPDATE ON todos BEGIN
        DELETE FROM todos_fts WHERE id = old.id;
        INSERT INTO todos_fts(id, title, description)
        VALUES (new.id, new.title, COALESCE(new.description, ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS todos_ad AFTER DELETE ON todos BEGIN
        DELETE FROM todos_fts WHERE id = old.id;
    END""",
    # -- Events triggers
    """CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
        INSERT INTO events_fts(id, title, description, location)
        VALUES (new.id, new.title, COALESCE(new.description, ''), COALESCE(new.location, ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
        DELETE FROM events_fts WHERE id = old.id;
        INSERT INTO events_fts(id, title, description, location)
        VALUES (new.id, new.title, COALESCE(new.description, ''), COALESCE(new.location, ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
        DELETE FROM events_fts WHERE id = old.id;
    END""",
    # -- Memos triggers
    """CREATE TRIGGER IF NOT EXISTS memos_ai AFTER INSERT ON memos BEGIN
        INSERT INTO memos_fts(id, title, content) VALUES (new.id, new.title, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS memos_au AFTER UPDATE ON memos BEGIN
        DELETE FROM memos_fts WHERE id = old.id;
        INSERT INTO memos_fts(id, title, content) VALUES (new.id, new.title, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS memos_ad AFTER DELETE ON memos BEGIN
        DELETE FROM memos_fts WHERE id = old.id;
    END""",
]

_FTS5_BACKFILL = [
    """INSERT INTO messages_fts(id, content)
        SELECT id, content FROM messages
        WHERE id NOT IN (SELECT id FROM messages_fts)""",
    """INSERT INTO todos_fts(id, title, description)
        SELECT id, title, COALESCE(description, '') FROM todos
        WHERE id NOT IN (SELECT id FROM todos_fts)""",
    """INSERT INTO events_fts(id, title, description, location)
        SELECT id, title, COALESCE(description, ''), COALESCE(location, '') FROM events
        WHERE id NOT IN (SELECT id FROM events_fts)""",
    """INSERT INTO memos_fts(id, title, content)
        SELECT id, title, content FROM memos
        WHERE id NOT IN (SELECT id FROM memos_fts)""",
]


async def init_db():
    # Ensure the data directory exists for SQLite
    db_path = settings.database_url.split("///")[-1]
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    from config import settings as app_settings
    os.makedirs(app_settings.upload_dir, exist_ok=True)

    async with engine.begin() as conn:
        from models import _register_all  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

        # Migrate existing DBs: add new columns (safe if already present)
        _ALTER_TABLE_STMTS = [
            "ALTER TABLE todos ADD COLUMN parent_id TEXT REFERENCES todos(id) ON DELETE SET NULL",
            "ALTER TABLE todos ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE todos ADD COLUMN source TEXT",
            "ALTER TABLE todos ADD COLUMN source_id TEXT",
            "ALTER TABLE todos ADD COLUMN assignee TEXT",
        ]
        for stmt in _ALTER_TABLE_STMTS:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists

        # Create FTS5 virtual tables, triggers, and backfill existing data
        for stmt in _FTS5_VIRTUAL_TABLES + _FTS5_TRIGGERS + _FTS5_BACKFILL:
            await conn.execute(text(stmt))


async def get_db():
    async with async_session_factory() as session:
        yield session
