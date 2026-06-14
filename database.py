import sqlite3
import os

DB_PATH = "bot_data.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            roblox_username TEXT NOT NULL,
            roblox_id TEXT,
            roblox_avatar_url TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            value INTEGER NOT NULL,
            image_url TEXT,
            source_url TEXT,
            added_by TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS inventories (
            discord_id TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (discord_id, item_id),
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_channels (
            guild_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            set_by TEXT,
            set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS value_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            old_value INTEGER NOT NULL,
            new_value INTEGER NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    """)

    conn.commit()
    conn.close()


def get_user(discord_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_roblox(roblox_username: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE LOWER(roblox_username) = LOWER(?)", (roblox_username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def register_user(discord_id: str, roblox_username: str, roblox_id: str, avatar_url: str):
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO users (discord_id, roblox_username, roblox_id, roblox_avatar_url)
           VALUES (?, ?, ?, ?)""",
        (discord_id, roblox_username, roblox_id, avatar_url),
    )
    conn.commit()
    conn.close()


def get_item(name: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM items WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_items():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_item(name: str, value: int, image_url: str, source_url: str, added_by: str):
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM items WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    if existing:
        conn.close()
        return None, "exists"
    conn.execute(
        "INSERT INTO items (name, value, image_url, source_url, added_by) VALUES (?, ?, ?, ?, ?)",
        (name, value, image_url, source_url, added_by),
    )
    conn.commit()
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return item_id, "ok"


def update_item_value(item_id: int, new_value: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return None
    old_value = row["value"]
    conn.execute(
        "INSERT INTO value_history (item_id, item_name, old_value, new_value) VALUES (?, ?, ?, ?)",
        (item_id, row["name"], old_value, new_value),
    )
    conn.execute(
        "UPDATE items SET value = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
        (new_value, item_id),
    )
    conn.commit()
    conn.close()
    return {"old": old_value, "new": new_value, "name": row["name"]}


def get_inventory(discord_id: str):
    conn = get_conn()
    rows = conn.execute(
        """SELECT i.*, it.name, it.value, it.image_url
           FROM inventories i
           JOIN items it ON i.item_id = it.id
           WHERE i.discord_id = ?
           ORDER BY it.name""",
        (discord_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_to_inventory(discord_id: str, item_id: int):
    conn = get_conn()
    existing = conn.execute(
        "SELECT quantity FROM inventories WHERE discord_id = ? AND item_id = ?",
        (discord_id, item_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE inventories SET quantity = quantity + 1 WHERE discord_id = ? AND item_id = ?",
            (discord_id, item_id),
        )
    else:
        conn.execute(
            "INSERT INTO inventories (discord_id, item_id) VALUES (?, ?)",
            (discord_id, item_id),
        )
    conn.commit()
    conn.close()


def get_item_owners(item_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT discord_id FROM inventories WHERE item_id = ?", (item_id,)
    ).fetchall()
    conn.close()
    return [r["discord_id"] for r in rows]


def get_ai_channel(guild_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT channel_id FROM ai_channels WHERE guild_id = ?", (guild_id,)
    ).fetchone()
    conn.close()
    return row["channel_id"] if row else None


def set_ai_channel(guild_id: str, channel_id: str, set_by: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ai_channels (guild_id, channel_id, set_by) VALUES (?, ?, ?)",
        (guild_id, channel_id, set_by),
    )
    conn.commit()
    conn.close()


def get_value_history(item_id: int, limit: int = 5):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM value_history WHERE item_id = ? ORDER BY changed_at DESC LIMIT ?",
        (item_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
