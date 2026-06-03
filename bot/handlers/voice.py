import logging

from aiogram import Bot, F, Router
from aiogram.types import Message

from bot import database
from bot.services import transcription_service, voice_service

logger = logging.getLogger(__name__)
router = Router(name="voice")


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

    status_msg = await message.reply(f"\U0001f3a4 Овозли хабар қабул қилинди ({duration_str}). Матнга айлантирилмоқда\u2026")

    transcript = await transcription_service.transcribe(local_path)

    if transcript:
        await database.repository.update_transcript(record_id, transcript)
        await status_msg.edit_text(
            f"\U0001f3a4 Сақланди ({duration_str})\n\n\U0001f4dd <b>Транскрипция:</b>\n{transcript}"
        )
        logger.info("Transcribed user_id=%d id=%d: %s", user.id, record_id, transcript[:60])
    else:
        await status_msg.edit_text(
            f"\U0001f3a4 Сақланди ({duration_str})\n\n\u26a0\ufe0f Транскрипция амалга ошмади."
        )