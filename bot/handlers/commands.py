from datetime import date, timedelta

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import database
from bot.services.summary_service import format_duration, get_or_generate_summary

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else ""
    await message.answer(
        f"\U0001f44b Assalomu alaykum, {name}!\n\n"
        "Men sizning ovozli xabarlaringizni saqlayman, matnga aylantirama "
        "va kunlik xulosalar yuborama.\n\n"
        "<b>Buyruqlar:</b>\n"
        "/today \u2014 bugungi xabarlar va transkripsiyalar\n"
        "/summary \u2014 bugungi qisqa statistika\n"
        "/yesterday \u2014 kechagi xulosa\n"
        "/search \u2014 transkripsiyalardan qidirish\n"
        "/stats \u2014 umumiy statistika\n"
        "/help \u2014 barcha buyruqlar"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Mavjud buyruqlar</b>\n\n"
        "/start \u2014 boshlash xabari\n"
        "/today \u2014 bugungi ovozli xabarlar va transkripsiyalar\n"
        "/summary \u2014 bugungi qisqa statistika\n"
        "/yesterday \u2014 kechagi xulosa\n"
        "/search &lt;so'z&gt; \u2014 barcha transkripsiyalardan qidirish\n"
        "/stats \u2014 umumiy ovoz statistikasi\n"
        "/help \u2014 shu xabar\n\n"
        "Ovozli xabar yuboring \u2014 avtomatik matnga aylantirama!"
    )


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    today = date.today()
    messages = await database.repository.get_voice_messages_by_date(user_id, today)
    if not messages:
        await message.answer(f"\U0001f50d Bugun ovozli xabar yo'q ({today.isoformat()}).")
        return
    total_duration = sum(m.get("duration") or 0 for m in messages)
    lines = [
        f"\U0001f4c5 <b>Bugun \u2014 {today.strftime('%d.%m.%Y')}</b>",
        f"\U0001f3a4 {len(messages)} ta xabar  |  \u23f1 {format_duration(total_duration)}",
        "",
    ]
    for i, msg in enumerate(messages, 1):
        time_str = (msg.get("created_at") or "")[11:16]
        transcript = msg.get("transcript") or "\u23f3 <i>transkripsiya qilinmoqda\u2026</i>"
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
        await message.answer(f"\U0001f50d Bugun ovozli xabar yo'q ({today.isoformat()}).")
        return
    total_duration = sum(m.get("duration") or 0 for m in messages)
    transcribed = sum(1 for m in messages if m.get("transcript"))
    await message.answer(
        f"\U0001f4ca <b>Bugungi xulosa \u2014 {today.strftime('%d.%m.%Y')}</b>\n\n"
        f"\U0001f3a4 Ovozli xabarlar: <b>{len(messages)}</b>\n"
        f"\U0001f4dd Transkripsiya: <b>{transcribed}/{len(messages)}</b>\n"
        f"\u23f1 Umumiy davomiylik: <b>{format_duration(total_duration)}</b>\n\n"
        "Barchasi: /today"
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
        await message.answer(f"\U0001f50d {yesterday.isoformat()} kuni ovozli xabar yo'q.")


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    if message.from_user is None:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Foydalanish: /search &lt;so'z&gt;\n"
            "Masalan: /search bank"
        )
        return
    query = parts[1].strip()
    results = await database.repository.search_transcripts(message.from_user.id, query)
    if not results:
        await message.answer(f'\U0001f50d "<b>{query}</b>" bo\'yicha natija topilmadi.')
        return
    lines = [f'\U0001f50d <b>"{query}"</b> \u2014 {len(results)} ta natija\n']
    for msg in results[:10]:
        date_str = (msg.get("created_at") or "")[:10]
        time_str = (msg.get("created_at") or "")[11:16]
        transcript = msg.get("transcript", "")
        lines.append(f"\U0001f4c5 {date_str} {time_str}\n{transcript}\n")
    if len(results) > 10:
        lines.append(f"<i>\u2026va yana {len(results) - 10} ta</i>")
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user is None:
        return
    stats = await database.repository.get_user_stats(message.from_user.id)
    if not stats or stats.get("total_messages", 0) == 0:
        await message.answer("\U0001f50d Hali ovozli xabar yo'q. Birinchi ovozli xabaringizni yuboring!")
        return
    first = (stats.get("first_message") or "")[:10] or "N/A"
    last = (stats.get("last_message") or "")[:10] or "N/A"
    await message.answer(
        "<b>\U0001f4c8 Ovoz statistikangiz</b>\n\n"
        f"\U0001f3a4 Jami xabarlar: <b>{stats['total_messages']}</b>\n"
        f"\u23f1 Jami davomiylik: <b>{format_duration(stats['total_duration'])}</b>\n"
        f"\U0001f4c5 Birinchi xabar: {first}\n"
        f"\U0001f4c5 Oxirgi xabar: {last}"
    )