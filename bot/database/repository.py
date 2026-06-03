import aiosqlite
from datetime import date
from typing import Optional
from bot.config import DB_PATH
from bot.database.models import (
    CREATE_VOICE_MESSAGES_TABLE,
    CREATE_DAILY_SUMMARIES_TABLE,
    MIGRATE_ADD_TRANSCRIPT,
)


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_VOICE_MESSAGES_TABLE)
        await db.execute(CREATE_DAILY_SUMMARIES_TABLE)
        # Non-destructive migration for existing databases
        try:
            await db.execute(MIGRATE_ADD_TRANSCRIPT)
        except Exception:
            pass  # Column already exists
        await db.commit()


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
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO voice_messages
            (user_id, username, first_name, file_id, file_unique_id, duration, file_size, local_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, first_name, file_id, file_unique_id, duration, file_size, local_path),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def update_transcript(record_id: int, transcript: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE voice_messages SET transcript = ? WHERE id = ?",
            (transcript, record_id),
        )
        await db.commit()


async def get_voice_messages_by_date(user_id: int, target_date: date) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM voice_messages
            WHERE user_id = ? AND DATE(created_at) = ?
            ORDER BY created_at
            """,
            (user_id, target_date.isoformat()),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def search_transcripts(user_id: int, query: str) -> list[dict]:
    """Case-insensitive full-text search across all transcripts for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM voice_messages
            WHERE user_id = ?
              AND transcript IS NOT NULL
              AND LOWER(transcript) LIKE LOWER(?)
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user_id, f"%{query}%"),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_users_with_messages_on_date(target_date: date) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT DISTINCT user_id, username, first_name
            FROM voice_messages
            WHERE DATE(created_at) = ?
            """,
            (target_date.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def save_daily_summary(
    user_id: int,
    summary_date: date,
    message_count: int,
    total_duration: int,
    summary_text: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO daily_summaries
            (user_id, summary_date, message_count, total_duration, summary_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, summary_date.isoformat(), message_count, total_duration, summary_text),
        )
        await db.commit()


async def get_user_summary(user_id: int, summary_date: date) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM daily_summaries
            WHERE user_id = ? AND summary_date = ?
            """,
            (user_id, summary_date.isoformat()),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_user_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                COUNT(*)                    AS total_messages,
                COALESCE(SUM(duration), 0)  AS total_duration,
                MIN(created_at)             AS first_message,
                MAX(created_at)             AS last_message
            FROM voice_messages
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {}
