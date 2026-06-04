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
        f"\U0001f44b Ассалому алайкум, {name}!\n\n"
        "Мен сизнинг овозли хабарларингизни сақлайман, матнга айлантираман "
        "ва кунлик хулосалар юбораман.\n\n"
        "<b>Буйруқлар:</b>\n"
        "/today \u2014 бугунги хабарлар ва транскрипциялар\n"
        "/summary \u2014 бугунги қисқа статистика\n"
        "/yesterday \u2014 кечаги хулоса\n"
        "/search \u2014 транскрипциялардан қидириш\n"
        "/stats \u2014 умумий статистика\n"
        "/help \u2014 барча буйруқлар"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Мавжуд буйруқлар</b>\n\n"
        "/start \u2014 бошлаш хабари\n"
        "/today \u2014 бугунги овозли хабарлар ва транскрипциялар\n"
        "/summary \u2014 бугунги қисқа статистика\n"
        "/yesterday \u2014 кечаги хулоса\n"
        "/search &lt;сўз&gt; \u2014 барча транскрипциялардан қидириш\n"
        "/stats \u2014 умумий овоз статистикаси\n"
        "/help \u2014 шу хабар\n\n"
        "Овозли хабар юборинг \u2014 автоматик матнга айлантираман!"
    )


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    today = date.today()
    messages = await database.repository.get_voice_messages_by_date(user_id, today)
    if not messages:
        await message.answer(f"\U0001f50d Бугун овозли хабар йўқ ({today.isoformat()}).")
        return
    total_duration = sum(m.get("duration") or 0 for m in messages)
    lines = [
        f"\U0001f4c5 <b>Бугун \u2014 {today.strftime('%d.%m.%Y')}</b>",
        f"\U0001f3a4 {len(messages)} та хабар  |  \u23f1 {format_duration(total_duration)}",
        "",
    ]
    for i, msg in enumerate(messages, 1):
        time_str = str(msg.get("created_at") or "")[11:16]
        transcript = msg.get("transcript") or "\u23f3 <i>транскрипция қилинмоқда\u2026</i>"
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
        await message.answer(f"\U0001f50d Бугун овозли хабар йўқ ({today.isoformat()}).")
        return
    total_duration = sum(m.get("duration") or 0 for m in messages)
    transcribed = sum(1 for m in messages if m.get("transcript"))
    await message.answer(
        f"\U0001f4ca <b>Бугунги хулоса \u2014 {today.strftime('%d.%m.%Y')}</b>\n\n"
        f"\U0001f3a4 Овозли хабарлар: <b>{len(messages)}</b>\n"
        f"\U0001f4dd Транскрипция: <b>{transcribed}/{len(messages)}</b>\n"
        f"\u23f1 Умумий давомийлик: <b>{format_duration(total_duration)}</b>\n\n"
        "Барчаси: /today"
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
        await message.answer(f"\U0001f50d {yesterday.isoformat()} куни овозли хабар йўқ.")


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    if message.from_user is None:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Фойдаланиш: /search &lt;сўз&gt;\n"
            "Масалан: /search банк"
        )
        return
    query = parts[1].strip()
    results = await database.repository.search_transcripts(message.from_user.id, query)
    if not results:
        await message.answer(f'\U0001f50d "<b>{query}</b>" бўйича натижа топилмади.')
        return
    lines = [f'\U0001f50d <b>"{query}"</b> \u2014 {len(results)} та натижа\n']
    for msg in results[:10]:
        date_str = (msg.get("created_at") or "")[:10]
        time_str = str(msg.get("created_at") or "")[11:16]
        transcript = msg.get("transcript", "")
        lines.append(f"\U0001f4c5 {date_str} {time_str}\n{transcript}\n")
    if len(results) > 10:
        lines.append(f"<i>\u2026ва яна {len(results) - 10} та</i>")
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user is None:
        return
    stats = await database.repository.get_user_stats(message.from_user.id)
    if not stats or stats.get("total_messages", 0) == 0:
        await message.answer("\U0001f50d Ҳали овозли хабар йўқ. Биринчи овозли хабарингизни юборинг!")
        return
    first = str(stats.get("first_message") or "")[:10] or "N/A"
    last = str(stats.get("last_message") or "")[:10] or "N/A"
    await message.answer(
        "<b>\U0001f4c8 Овоз статистикангиз</b>\n\n"
        f"\U0001f3a4 Жами хабарлар: <b>{stats['total_messages']}</b>\n"
        f"\u23f1 Жами давомийлик: <b>{format_duration(stats['total_duration'])}</b>\n"
        f"\U0001f4c5 Биринчи хабар: {first}\n"
        f"\U0001f4c5 Охирги хабар: {last}"
    )