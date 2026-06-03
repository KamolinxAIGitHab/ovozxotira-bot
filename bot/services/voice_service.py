import logging
import os
from datetime import datetime
from typing import Optional

from aiogram import Bot
from aiogram.types import Voice

from bot.config import VOICE_DIR

logger = logging.getLogger(__name__)


async def download_voice(bot: Bot, voice: Voice, user_id: int) -> Optional[str]:
    """Download a voice message and save it locally. Returns the local file path."""
    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        user_dir = os.path.join(VOICE_DIR, str(user_id), date_str)
        os.makedirs(user_dir, exist_ok=True)

        tg_file = await bot.get_file(voice.file_id)
        local_path = os.path.join(user_dir, f"{voice.file_unique_id}.ogg")
        await bot.download_file(tg_file.file_path, local_path)  # type: ignore[arg-type]
        return local_path
    except Exception:
        logger.exception("Failed to download voice message file_id=%s", voice.file_id)
        return None
