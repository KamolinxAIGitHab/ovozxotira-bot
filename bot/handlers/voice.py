import html
import logging
import time

from aiogram import Bot, F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import database
from bot.services import transcription_service, voice_service
from bot.services.summary_service import format_duration
from bot.timeutil import format_elapsed, reply_time

logger = logging.getLogger(__name__)

router = Router(name="voice")

MAX_MSG_LEN = 4000


def split_text(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    """Узун матнни бўлаклarga бўлиш."""
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_at = text.rfind(" ", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].strip()
    return parts


@router.message(F.voice)
async def handle_voice_message(message: Message, bot: Bot) -> None:
    user = message.from_user
    voice = message.voice

    if user is None or voice is None:
        return

    local_path = await voice_service.download_voice(bot, voice, user.id)

    record_id = await database.repository.save_voice_message(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        file_id=voice.file_id,
        file_unique_id=voice.file_unique_id,
        duration=voice.duration,
        file_size=voice.file_size,
        local_path=local_path,
    )

    duration_str = f"{voice.duration} сек" if voice.duration else "?"

    if not local_path:
        await message.reply(f"\u26a0\ufe0f Файл юклаб олинмади ({duration_str}).")
        return

    status_msg = await message.reply(
        f"\U0001f3a4 Овозли хабар қабул қилинди ({duration_str}). Матнга айлантирилмоқда\u2026"
    )

    mode = await database.repository.get_lang_mode(user.id)
    started = time.monotonic()
    transcript = await transcription_service.transcribe(
        local_path, mode, duration=voice.duration
    )
    elapsed = format_elapsed(time.monotonic() - started)

    duration_line = (
        f"🎙 Овоз давомийлиги: {format_duration(voice.duration)}"
        if voice.duration
        else "🎙 Овоз давомийлиги: ?"
    )
    info = f"{reply_time()}"
    meta = (
        f"🎤 Сақланди  🕒 {info}\n"
        f"{duration_line}\n"
        f"⏱ Транскрипция вақти: {elapsed}\n\n"
    )

    if transcript:
        await database.repository.update_transcript(record_id, transcript)

        header = meta + "📝 <b>Транскрипция:</b>\n"
        parts = [f"<pre>{html.escape(p)}</pre>" for p in split_text(transcript, 3000)]
        keyboard = _result_keyboard(record_id, transcript) if record_id else None

        await status_msg.edit_text(header + parts[0], reply_markup=keyboard)
        for part in parts[1:]:
            await message.reply(part)

        logger.info("Transcribed user_id=%d id=%d: %s", user.id, record_id, transcript[:60])
    else:
        await status_msg.edit_text(meta + "⚠️ Транскрипция амалга ошмади.")


def _result_keyboard(record_id: int, transcript: str) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    # Telegram тугма орқали тўғридан-тўғри нусхалашни фақат 256 белгигача қўллайди
    if len(transcript) <= 256:
        row.append(InlineKeyboardButton(text="📋 Нусхалаш", copy_text=CopyTextButton(text=transcript)))
    row.append(InlineKeyboardButton(text="💬 Матн", callback_data=f"tx:{record_id}"))
    row.append(InlineKeyboardButton(text="📄 TXT", callback_data=f"tf:{record_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def _load_transcript(callback: CallbackQuery) -> tuple[int, str | None]:
    try:
        record_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        return 0, None
    transcript = await database.repository.get_transcript(record_id, callback.from_user.id)
    return record_id, transcript


@router.callback_query(F.data.startswith("tx:"))
async def cb_send_text(callback: CallbackQuery) -> None:
    """Матнни оддий (форматсиз) хабар қилиб юборади: уни босиб туриб нусхалаш мумкин."""
    record_id, transcript = await _load_transcript(callback)
    if not transcript or not isinstance(callback.message, Message):
        await callback.answer("Матн топилмади.", show_alert=True)
        return
    for part in split_text(transcript, 3500):
        await callback.message.answer(part, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("tf:"))
async def cb_send_file(callback: CallbackQuery) -> None:
    record_id, transcript = await _load_transcript(callback)
    if not transcript or not isinstance(callback.message, Message):
        await callback.answer("Матн топилмади.", show_alert=True)
        return
    await callback.message.answer_document(
        BufferedInputFile(transcript.encode("utf-8"), filename=f"transcript_{record_id}.txt"),
        caption="📄 Транскрипция матни",
    )
    await callback.answer()
