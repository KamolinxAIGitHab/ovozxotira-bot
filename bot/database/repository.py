import os
import asyncpg
from datetime import date
from typing import Optional

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool


async def init_db() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_messages (
                id              SERIAL PRIMARY KEY,
                user_id         BIGINT NOT NULL,
                username        TEXT,
                first_name      TEXT,
                file_id         TEXT NOT NULL,
                file_unique_id  TEXT NOT NULL UNIQUE,
                duration        INTEGER,
                file_size       INTEGER,
                local_path      TEXT,
                transcript      TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                id              SERIAL PRIMARY KEY,
                user_id         BIGINT NOT NULL,
                summary_date    DATE NOT NULL,
                message_count   INTEGER NOT NULL,
                total_duration  INTEGER NOT NULL DEFAULT 0,
                summary_text    TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, summary_date)
            )
        """)


async def save_voice_message(
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    file_id: str,
    file_unique_id: str,
    duration: Optional[int],
    file_size: Optional[int],
    local_path: Optional[str],
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO voice_messages
            (user_id, username, first_name, file_id, file_unique_id, duration, file_size, local_path)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (file_unique_id) DO NOTHING
            RETURNING id
            """,
            user_id, username, first_name, file_id, file_unique_id, duration, file_size, local_path,
        )
        return row["id"] if row else 0


async def update_transcript(record_id: int, transcript: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE voice_messages SET transcript = $1 WHERE id = $2",
            transcript, record_id,
        )


async def get_voice_messages_by_date(user_id: int, target_date: date) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM voice_messages
            WHERE user_id = $1 AND DATE(created_at) = $2
            ORDER BY created_at
            """,
            user_id, target_date,
        )
        return [dict(row) for row in rows]


async def search_transcripts(user_id: int, query: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM voice_messages
            WHERE user_id = $1
              AND transcript IS NOT NULL
              AND LOWER(transcript) LIKE LOWER($2)
            ORDER BY created_at DESC
            LIMIT 20
            """,
            user_id, f"%{query}%",
        )
        return [dict(row) for row in rows]


async def get_all_users_with_messages_on_date(target_date: date) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT user_id, username, first_name
            FROM voice_messages
            WHERE DATE(created_at) = $1
            """,
            target_date,
        )
        return [dict(row) for row in rows]


async def save_daily_summary(
    user_id: int,
    summary_date: date,
    message_count: int,
    total_duration: int,
    summary_text: str,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO daily_summaries
            (user_id, summary_date, message_count, total_duration, summary_text)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, summary_date)
            DO UPDATE SET
                message_count = EXCLUDED.message_count,
                total_duration = EXCLUDED.total_duration,
                summary_text = EXCLUDED.summary_text
            """,
            user_id, summary_date, message_count, total_duration, summary_text,
        )


async def get_user_summary(user_id: int, summary_date: date) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM daily_summaries
            WHERE user_id = $1 AND summary_date = $2
            """,
            user_id, summary_date,
        )
        return dict(row) if row else None


async def get_user_stats(user_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                    AS total_messages,
                COALESCE(SUM(duration), 0)  AS total_duration,
                MIN(created_at)             AS first_message,
                MAX(created_at)             AS last_message
            FROM voice_messages
            WHERE user_id = $1
            """,
            user_id,
        )
        return dict(row) if row else {}