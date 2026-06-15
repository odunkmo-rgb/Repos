"""
dbutil.py — Unified async database layer.

* DATABASE_URL env var set  → PostgreSQL via asyncpg (Railway / any PG host)
* DATABASE_URL not set      → SQLite via aiosqlite  (local / Replit dev)

Drop-in replacement for `aiosqlite.connect(DB_PATH)`:
    async with db_connect() as db:
        await db.execute(sql, params)
        await db.commit()

SQL is written in SQLite dialect (?-params); the layer converts to PG
($1,$2…) automatically when PostgreSQL is active.
"""

import os
import re
import aiosqlite

DB_PATH      = "bot/bot.db"
# Use BOT_DATABASE_URL (not DATABASE_URL) so we don't collide with the
# API-server's Replit PostgreSQL.  Set BOT_DATABASE_URL on Railway to
# enable persistent PostgreSQL storage; leave it unset for SQLite on Replit.
DATABASE_URL = os.getenv("BOT_DATABASE_URL")

_pg_pool = None


# ─── SQL ADAPTATION ──────────────────────────────────────────────────────────

# Primary-key columns per table — used to build ON CONFLICT clause
_TABLE_PK: dict[str, list[str]] = {
    "settings":            ["guild_id"],
    "roblox_bagla":        ["discord_id"],
    "degerler_cache":      ["esya_adi"],
    "bot_ayarlari":        ["anahtar"],
    "kullanici_tercihler": ["discord_id", "anahtar"],
    "ai_kullanici_stil":   ["guild_id", "user_id"],
    "ai_hafiza":           ["guild_id", "user_id"],
    "envanter":            [],          # uses BIGSERIAL id, no upsert needed
    "kullanim_log":        [],
    "hata_log":            [],
}


def _convert_upsert(sql: str) -> str:
    """Convert INSERT OR REPLACE … to INSERT … ON CONFLICT DO UPDATE SET …"""
    m = re.match(
        r"(?i)INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*(VALUES\s*.+)",
        sql.strip(), re.DOTALL,
    )
    if not m:
        # Can't parse — fall back to safe INSERT (will error on dup, but rare)
        return re.sub(r"(?i)\bINSERT\s+OR\s+REPLACE\b", "INSERT", sql)

    table     = m.group(1)
    cols_raw  = m.group(2)
    values_pg = m.group(3)
    cols      = [c.strip() for c in cols_raw.split(",")]
    pk_cols   = set(_TABLE_PK.get(table.lower(), []))
    upd_cols  = [c for c in cols if c.lower() not in pk_cols]

    base = f"INSERT INTO {table} ({cols_raw}) {values_pg}"

    if pk_cols and upd_cols:
        conflict = ", ".join(pk_cols)
        updates  = ", ".join(f"{c} = EXCLUDED.{c}" for c in upd_cols)
        return f"{base} ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    elif pk_cols:
        conflict = ", ".join(pk_cols)
        return f"{base} ON CONFLICT ({conflict}) DO NOTHING"
    else:
        return f"{base} ON CONFLICT DO NOTHING"


def _to_pg(sql: str) -> str:
    """Translate SQLite-flavoured SQL to PostgreSQL."""
    # Handle INSERT OR REPLACE before anything else
    if re.search(r"(?i)\bINSERT\s+OR\s+REPLACE\b", sql):
        sql = _convert_upsert(sql)

    # ? → $1 $2 ...
    n = [0]
    def _ph(_m):
        n[0] += 1
        return f"${n[0]}"
    sql = re.sub(r"\?", _ph, sql)

    # AUTOINCREMENT primary keys
    sql = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        sql, flags=re.IGNORECASE,
    )
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.IGNORECASE)

    # date defaults
    sql = sql.replace("(datetime('now'))", "(NOW()::TEXT)")
    sql = sql.replace("datetime('now')", "NOW()::TEXT")

    return sql


# ─── POSTGRESQL CURSOR SHIM ───────────────────────────────────────────────────

class _PgCursor:
    """Mimics aiosqlite cursor: fetchone / fetchall / async-iteration."""

    def __init__(self, rows):
        self._rows = list(rows) if rows else []
        self._idx  = 0

    async def fetchone(self):
        return tuple(self._rows[0].values()) if self._rows else None

    async def fetchall(self):
        return [tuple(r.values()) for r in self._rows]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return tuple(row.values())


class _PgExecCM:
    """Returned by _PgConn.execute() — usable as `async with` or awaited."""

    def __init__(self, conn, sql: str, params):
        self._conn   = conn
        self._sql    = _to_pg(sql)
        self._params = tuple(params)

    async def _run(self):
        upper = self._sql.lstrip().upper()
        if upper.startswith(("SELECT", "WITH")):
            rows = await self._conn.fetch(self._sql, *self._params)
            return _PgCursor(rows)
        else:
            await self._conn.execute(self._sql, *self._params)
            return _PgCursor([])

    # Support: async with db.execute(...) as cur:
    async def __aenter__(self):
        self._cursor = await self._run()
        return self._cursor

    async def __aexit__(self, *_):
        pass

    # Support: cur = await db.execute(...)
    def __await__(self):
        return self._run().__await__()


# ─── POSTGRESQL CONNECTION SHIM ───────────────────────────────────────────────

class _PgConn:
    """Wraps an asyncpg connection to look like aiosqlite.Connection."""

    def __init__(self, raw_conn):
        self._raw = raw_conn

    def execute(self, sql: str, params=()):
        return _PgExecCM(self._raw, sql, params)

    async def commit(self):
        pass  # transaction committed in __aexit__ of _PgConnCM

    async def executescript(self, script: str):
        stmts = [s.strip() for s in script.split(";") if s.strip()]
        for stmt in stmts:
            pg = _to_pg(stmt)
            try:
                await self._raw.execute(pg)
            except Exception as exc:
                msg = str(exc).lower()
                if any(k in msg for k in ("already exists", "duplicate column", "duplicate key")):
                    continue
                raise


class _PgConnCM:
    """Async context manager: acquires a connection + wraps in transaction."""

    async def __aenter__(self) -> _PgConn:
        self._pool = await _get_pool()
        self._raw  = await self._pool.acquire()
        self._tr   = self._raw.transaction()
        await self._tr.start()
        return _PgConn(self._raw)

    async def __aexit__(self, exc_type, *_):
        if exc_type:
            await self._tr.rollback()
        else:
            await self._tr.commit()
        await self._pool.release(self._raw)


# ─── POOL MANAGEMENT ─────────────────────────────────────────────────────────

async def _get_pool():
    global _pg_pool
    if _pg_pool is None:
        import asyncpg  # lazy import — not installed when using SQLite
        _pg_pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=2, max_size=10
        )
    return _pg_pool


async def close_pool():
    """Call on bot shutdown to gracefully close the PG pool."""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def db_connect():
    """
    Drop-in replacement for `aiosqlite.connect(DB_PATH)`.

    Usage:
        async with db_connect() as db:
            await db.execute("INSERT INTO ...", (val,))
            await db.commit()
    """
    if DATABASE_URL:
        return _PgConnCM()
    return aiosqlite.connect(DB_PATH)
