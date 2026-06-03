import logging
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
client = AsyncOpenAI()

async def transcribe(audio_path: str) -> Optional[str]:
    try:
        with open(audio_path, "rb") as f:
            result = await client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=f,
                prompt="Ushbu audio O'zbek tilida. Iltimos, O'zbek tilida transkripsiya qiling."
            )
        return result.text or None
    except Exception:
        logger.exception("Transcription failed: %s", audio_path)
        return None
