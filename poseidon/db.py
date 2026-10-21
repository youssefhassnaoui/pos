"""Tenant-scoped SQLite persistence, with transactional submission limits."""

from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
 user_id INTEGER NOT NULL, name TEXT NOT NULL, url TEXT NOT NULL,
 reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 reviewer_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_submissions_guild_status ON submissions(guild_id,status);
CREATE INDEX IF NOT EXISTS idx_submissions_user_time ON submissions(guild_id,user_id,created_at);
CREATE TABLE IF NOT EXISTS bookmarks (
 user_id INTEGER NOT NULL, slug TEXT NOT NULL,
 PRIMARY KEY(user_id,slug)
);
"""


class SubmissionLimit(ValueError):
    pass


class Database:
    def __init__(self, path):
        self.path = str(path)

    async def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA)
            await db.commit()

    async def submit(self, guild_id, user_id, name, url, reason):
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "SELECT COUNT(*) FROM submissions WHERE guild_id=? AND user_id=? AND created_at >= datetime('now','-1 hour')",
                (guild_id, user_id),
            )
            if (await cur.fetchone())[0] >= 5:
                raise SubmissionLimit("You can submit up to five resources per server per hour.")
            cur = await db.execute(
                "SELECT 1 FROM submissions WHERE guild_id=? AND url=? AND status='pending'",
                (guild_id, url),
            )
            if await cur.fetchone():
                raise SubmissionLimit("This URL is already awaiting review in this server.")
            cur = await db.execute(
                "INSERT INTO submissions(guild_id,user_id,name,url,reason) VALUES (?,?,?,?,?)",
                (guild_id, user_id, name, url, reason),
            )
            await db.commit()
            return cur.lastrowid

    async def pending(self, guild_id):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM submissions WHERE guild_id=? AND status='pending' ORDER BY id LIMIT 10",
                (guild_id,),
            )
            return [dict(x) for x in await cur.fetchall()]

    async def review(self, guild_id, submission_id, reviewer_id, status):
        if status not in ("approved", "rejected"):
            raise ValueError("Invalid review decision.")
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE submissions SET status=?,reviewer_id=? WHERE id=? AND guild_id=? AND status='pending'",
                (status, reviewer_id, submission_id, guild_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def toggle_bookmark(self, user_id, slug):
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "DELETE FROM bookmarks WHERE user_id=? AND slug=?", (user_id, slug)
            )
            added = cur.rowcount == 0
            if added:
                cur = await db.execute("SELECT COUNT(*) FROM bookmarks WHERE user_id=?", (user_id,))
                if (await cur.fetchone())[0] >= 100:
                    raise ValueError("Bookmark limit reached (100). Remove a bookmark first.")
                await db.execute("INSERT INTO bookmarks VALUES (?,?)", (user_id, slug))
            await db.commit()
            return added

    async def bookmarks(self, user_id):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT slug FROM bookmarks WHERE user_id=? ORDER BY slug", (user_id,)
            )
            return [row[0] for row in await cur.fetchall()]
