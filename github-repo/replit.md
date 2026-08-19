# Mm2 Discord Bot

Python Discord bot for Roblox/MM2 account linking, inventory tracking, item
value lookups, persistent AI conversations, and server administration.

## Run & Operate

- `python main.py` — start the Discord bot
- `pnpm install` — install the workspace packages used by the supporting API
- `python -m py_compile main.py dbutil.py database.py` — syntax check

Required environment:

- `DISCORD_TOKEN` or `BOT_TOKEN` — Discord bot token
- `GROQ_API_KEY` — Groq API key for the AI channel
- `DATABASE_URL` or `BOT_DATABASE_URL` — persistent PostgreSQL connection

Optional environment:

- `BOT_DATA_DIR` — absolute directory for local SQLite development fallback
- `MAINTENANCE_NOTICE_VERSION` — changes the one-time bilingual announcement key

## Stack

- Python 3.12, discord.py, aiohttp, aiosqlite
- Groq's OpenAI-compatible chat API
- PostgreSQL through asyncpg in hosted environments
- SQLite only as a local-development fallback

## Where things live

- `main.py` — bot events, slash commands, AI, logging, and announcement flow
- `dbutil.py` — PostgreSQL/SQLite-compatible async database layer
- `database.py` — legacy synchronous data helpers kept for compatibility
- `requirements.txt` — Python dependencies

## Architecture decisions

- Global slash commands are synced once during `setup_hook`; stale guild-scoped
  copies are removed once to prevent duplicate command entries.
- PostgreSQL is the persistence backend whenever `DATABASE_URL` or
  `BOT_DATABASE_URL` is available, so changing the bot host does not remove data.
- Groq model IDs are validated against `/models` and cached briefly instead of
  relying on a permanently valid hard-coded list.
- The bilingual maintenance announcement is sent only to explicitly named bot
  command channels and is stored as a versioned database setting to avoid spam.

## Product

Users can link Roblox accounts, manage MM2 inventories, query item values,
configure an AI conversation channel, choose AI languages, and administer bot
settings through Discord slash commands.

## User preferences

- Maintenance messages must be bilingual (Turkish and English).
- The maintenance message targets the bot-command channels belonging to the two
  configured Discord servers in `main.py`.

## Gotchas

- Do not commit tokens or database URLs. Store them in Replit Secrets or the
  environment.
- A local SQLite database cannot provide host-independent persistence; configure
  PostgreSQL before moving or redeploying the bot.
- If a command channel uses a different name, add that normalized name to
  `ANNOUNCEMENT_CHANNEL_NAMES` before enabling the announcement.

## Pointers

- The runtime database schema is initialized and migrated by `init_db()` in
  `main.py`.
