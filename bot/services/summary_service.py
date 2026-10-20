import html
import logging
from datetime import date

from aiogram import Bot

from bot import database
from bot.textutil import chunk_text
from bot.timeutil import fmt_time, today_local

logger = logging.getLogger(__name__)


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сония"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} дақиқа {secs} сония"
    hours, mins = divmod(minutes, 60)
    return f"{hours} соат {mins} дақиқа"


def _build_summary_text(target_date: date, messages: list[dict]) -> str:
    count = len(messages)
    total_duration = sum(m.get("duration") or 0 for m in messages)

    lines = [
        f"\U0001f4ca <b>Кунлик хулоса \u2014 {target_date.strftime('%d.%m.%Y')}</b>",
        f"\U0001f3a4 {count} та хабар  |  \u23f1 {format_duration(total_duration)}",
        "",
    ]

    for i, msg in enumerate(messages, 1):
        time_str = fmt_time(msg.get("created_at"))
        if msg.get("transcript"):
            transcript = html.escape(msg["transcript"])
        else:
            transcript = "<i>транскрипция мавжуд эмас</i>"
        lines.append(f"{i}. [{time_str}] {transcript}")

    return "\n".join(lines)


async def generate_daily_summary(bot: Bot, target_date: date | None = None) -> None:
    if target_date is None:
        target_date = today_local()

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
            for part in chunk_text(summary_text):
                await bot.send_message(user_id, part)
            logger.info("Summary sent to user_id=%d", user_id)
        except Exception:
            logger.exception("Failed to send summary to user_id=%d", user_id)


async def get_or_generate_summary(bot: Bot, user_id: int, target_date: date) -> str | None:
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