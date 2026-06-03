import logging
from datetime import date, timedelta

from aiogram import Bot

from bot import database

logger = logging.getLogger(__name__)


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m {secs}s"


def _build_summary_text(target_date: date, messages: list[dict]) -> str:
    count = len(messages)
    total_duration = sum(m.get("duration") or 0 for m in messages)

    lines = [
        f"📊 <b>Daily Voice Summary — {target_date.strftime('%B %d, %Y')}</b>",
        f"🎤 {count} messages  |  ⏱ {format_duration(total_duration)} total",
        "",
    ]

    for i, msg in enumerate(messages, 1):
        time_str = (msg.get("created_at") or "")[ 11:16]  # HH:MM
        transcript = msg.get("transcript") or "<i>transcription unavailable</i>"
        lines.append(f"{i}. [{time_str}] {transcript}")

    return "\n".join(lines)


async def generate_daily_summary(bot: Bot, target_date: date | None = None) -> None:
    """Generate and send daily summaries based on transcripts to all active users."""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    users = await database.repository.get_all_users_with_messages_on_date(target_date)
    logger.info("Generating summaries for %d users on %s", len(users), target_date)

    for user in users:
        user_id: int = user["user_id"]
        messages = await database.repository.get_voice_messages_by_date(user_id, target_date)

        if not messages:
            continue

        total_duration = sum(m.get("duration") or 0 for m in messages)
        summary_text = _build_summary_text(target_date, messages)

        await database.repository.save_daily_summary(
            user_id=user_id,
            summary_date=target_date,
            message_count=len(messages),
            total_duration=total_duration,
            summary_text=summary_text,
        )

        try:
            await bot.send_message(user_id, summary_text)
            logger.info("Summary sent to user_id=%d", user_id)
        except Exception:
            logger.exception("Failed to send summary to user_id=%d", user_id)


async def get_or_generate_summary(bot: Bot, user_id: int, target_date: date) -> str | None:
    """Return cached summary text or generate on demand."""
    existing = await database.repository.get_user_summary(user_id, target_date)
    if existing:
        return existing["summary_text"]

    messages = await database.repository.get_voice_messages_by_date(user_id, target_date)
    if not messages:
        return None

    total_duration = sum(m.get("duration") or 0 for m in messages)
    summary_text = _build_summary_text(target_date, messages)

    await database.repository.save_daily_summary(
        user_id=user_id,
        summary_date=target_date,
        message_count=len(messages),
        total_duration=total_duration,
        summary_text=summary_text,
    )
    return summary_text
