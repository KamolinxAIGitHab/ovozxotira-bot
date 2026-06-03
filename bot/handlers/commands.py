from datetime import date, timedelta

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import database
from bot.services.summary_service import format_duration, get_or_generate_summary

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else "there"
    await message.answer(
        f"👋 Hello, {name}!\n\n"
        "I save your voice messages, transcribe them with Whisper, "
        "and send you daily summaries.\n\n"
        "<b>Commands:</b>\n"
        "/today — today's messages with transcripts\n"
        "/summary — today's quick stats\n"
        "/yesterday — yesterday's full summary\n"
        "/search — search through transcripts\n"
        "/stats — all-time statistics\n"
        "/help — full command list"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Available commands</b>\n\n"
        "/start — welcome message\n"
        "/today — today's voice messages with transcripts\n"
        "/summary — today's quick voice stats\n"
        "/yesterday — yesterday's full summary\n"
        "/search &lt;word&gt; — search in all transcripts\n"
        "/stats — all-time voice statistics\n"
        "/help — this message\n\n"
        "Send a voice message and I'll transcribe it automatically!"
    )


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    today = date.today()
    messages = await database.repository.get_voice_messages_by_date(user_id, today)

    if not messages:
        await message.answer(f"📭 No voice messages today ({today.isoformat()}).")
        return

    total_duration = sum(m.get("duration") or 0 for m in messages)
    lines = [
        f"📅 <b>Today — {today.strftime('%B %d, %Y')}</b>",
        f"🎤 {len(messages)} messages  |  ⏱ {format_duration(total_duration)}",
        "",
    ]
    for i, msg in enumerate(messages, 1):
        time_str = (msg.get("created_at") or "")[11:16]
        transcript = msg.get("transcript") or "⏳ <i>transcribing…</i>"
        lines.append(f"{i}. [{time_str}] {transcript}")

    await message.answer("\n".join(lines))


@router.message(Command("summary"))
async def cmd_summary(message: Message) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    today = date.today()
    messages = await database.repository.get_voice_messages_by_date(user_id, today)

    if not messages:
        await message.answer(f"📭 No voice messages today ({today.isoformat()}).")
        return

    total_duration = sum(m.get("duration") or 0 for m in messages)
    transcribed = sum(1 for m in messages if m.get("transcript"))
    await message.answer(
        f"📊 <b>Today's Summary — {today.strftime('%B %d, %Y')}</b>\n\n"
        f"🎤 Voice messages: <b>{len(messages)}</b>\n"
        f"📝 Transcribed: <b>{transcribed}/{len(messages)}</b>\n"
        f"⏱ Total duration: <b>{format_duration(total_duration)}</b>\n\n"
        "Use /today to see all transcripts."
    )


@router.message(Command("yesterday"))
async def cmd_yesterday(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return

    yesterday = date.today() - timedelta(days=1)
    summary_text = await get_or_generate_summary(bot, message.from_user.id, yesterday)

    if summary_text:
        await message.answer(summary_text)
    else:
        await message.answer(f"📭 No voice messages on {yesterday.isoformat()}.")


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    if message.from_user is None:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Usage: /search &lt;word&gt;\n"
            "Example: /search meeting"
        )
        return

    query = parts[1].strip()
    results = await database.repository.search_transcripts(message.from_user.id, query)

    if not results:
        await message.answer(f'🔍 No results found for "<b>{query}</b>".')
        return

    lines = [f'🔍 <b>"{query}"</b> — {len(results)} result(s)\n']
    for msg in results[:10]:
        date_str = (msg.get("created_at") or "")[:10]
        time_str = (msg.get("created_at") or "")[11:16]
        transcript = msg.get("transcript", "")
        lines.append(f"📅 {date_str} {time_str}\n{transcript}\n")

    if len(results) > 10:
        lines.append(f"<i>…and {len(results) - 10} more</i>")

    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user is None:
        return

    stats = await database.repository.get_user_stats(message.from_user.id)

    if not stats or stats.get("total_messages", 0) == 0:
        await message.answer("📭 No voice messages yet. Send one to get started!")
        return

    first = (stats.get("first_message") or "")[:10] or "N/A"
    last = (stats.get("last_message") or "")[:10] or "N/A"

    await message.answer(
        "<b>📈 Your Voice Statistics</b>\n\n"
        f"🎤 Total messages: <b>{stats['total_messages']}</b>\n"
        f"⏱ Total duration: <b>{format_duration(stats['total_duration'])}</b>\n"
        f"📅 First message: {first}\n"
        f"📅 Last message: {last}"
    )
