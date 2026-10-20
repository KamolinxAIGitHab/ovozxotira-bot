import asyncio
import logging
import os
import re
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
client = AsyncOpenAI()

TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o-mini")

PROMPT_UZ = (
    "Bu o'zbek tilidagi suhbat. "
    "Ucell, Uztelekom, Uzonline, internet, bank, shartnoma, xarid."
)
PROMPT_RU = "Это разговор на русском языке."

_CYR = re.compile(r"[Ѐ-ӿ]")
_LAT = re.compile(r"[A-Za-z]")

_CONVERT_SYSTEM = (
    "You are a precise Uzbek script converter. Convert the user's Uzbek text "
    "from {src} script to {dst} script. Change ONLY the script: do not translate, "
    "do not correct, shorten or add anything, keep punctuation, digits and line "
    "breaks. Keep Latin-written brand names (e.g. Ucell, Uztelekom) unchanged. "
    "Follow the standard Uzbek orthography: o' = ў, g' = ғ, sh = ш, ch = ч, "
    "ng = нг, q = қ, h = ҳ (x = х), yo = ё, yu = ю, ya = я, ye = е (word start) "
    "or ye, e = э at word start. Output only the converted text."
)


def _script_counts(text: str) -> tuple[int, int]:
    return len(_CYR.findall(text)), len(_LAT.findall(text))


async def _detect_language(audio_path: str) -> str:
    """Returns 'ru' if the speech is Russian, otherwise 'uz'."""
    try:
        with open(audio_path, "rb") as f:
            result = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
            )
        detected = (getattr(result, "language", "") or "").lower()
        logger.info("Detected language: %s", detected)
        return "ru" if detected in ("russian", "ru") else "uz"
    except Exception:
        logger.exception("Language detection failed, assuming uz")
        return "uz"


async def _call(model: str, audio_path: str, lang: Optional[str], prompt: str) -> Optional[str]:
    kwargs = {"model": model, "prompt": prompt}
    if lang:
        kwargs["language"] = lang
    with open(audio_path, "rb") as f:
        result = await client.audio.transcriptions.create(file=f, **kwargs)
    return (result.text or "").strip() or None


async def _transcribe_ru(audio_path: str) -> Optional[str]:
    return await _call("gpt-4o-transcribe", audio_path, "ru", PROMPT_RU)


async def _transcribe_uz(audio_path: str) -> Optional[str]:
    # gpt-4o-transcribe does not accept language="uz" (HTTP 400), so Uzbek
    # goes through whisper-1, which supports it. If that fails, fall back to
    # gpt-4o-transcribe without a language hint.
    try:
        text = await _call("whisper-1", audio_path, "uz", PROMPT_UZ)
        if text:
            return text
    except Exception:
        logger.exception("whisper-1 (uz) failed, falling back")
    return await _call("gpt-4o-transcribe", audio_path, None, PROMPT_UZ)


async def _convert_script(text: str, target: str) -> str:
    """target: 'cyrillic' or 'latin'. On any error the original text is returned."""
    src, dst = ("Latin", "Cyrillic") if target == "cyrillic" else ("Cyrillic", "Latin")
    try:
        resp = await client.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": _CONVERT_SYSTEM.format(src=src, dst=dst)},
                {"role": "user", "content": text},
            ],
        )
        converted = (resp.choices[0].message.content or "").strip()
        return converted or text
    except Exception:
        logger.exception("Script conversion failed")
        return text


async def _translate_to_russian(text: str) -> str:
    """Translate Uzbek text to Russian. On any error the original text is returned."""
    try:
        resp = await client.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Translate the user's Uzbek text (Latin or Cyrillic script) "
                        "into natural, accurate Russian. Keep names, numbers and "
                        "brand names. Output only the translation."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        return (resp.choices[0].message.content or "").strip() or text
    except Exception:
        logger.exception("Translation to Russian failed")
        return text


async def transcribe(audio_path: str, mode: str = "uz_cyr") -> Optional[str]:
    """mode: 'uz_cyr' | 'uz_lat' | 'ru'.

    Language detection and the Uzbek transcription run in parallel (faster).
    Russian speech is always transcribed as Russian. Uzbek speech is returned
    in Cyrillic or Latin script (uz_cyr / uz_lat), or translated into Russian
    (ru).
    """
    try:
        lang, uz_text = await asyncio.gather(
            _detect_language(audio_path),
            _transcribe_uz(audio_path),
            return_exceptions=True,
        )
        if isinstance(lang, BaseException):
            lang = "uz"
        if lang == "ru":
            return await _transcribe_ru(audio_path)
        if isinstance(uz_text, BaseException):
            logger.error("Uzbek transcription failed: %r", uz_text)
            return None
        text = uz_text
        if not text:
            return None
        if mode == "ru":
            return await _translate_to_russian(text)

        cyr, lat = _script_counts(text)
        if mode == "uz_cyr" and lat > cyr:
            text = await _convert_script(text, "cyrillic")
        elif mode == "uz_lat" and cyr > lat:
            text = await _convert_script(text, "latin")
        return text
    except Exception:
        logger.exception("Transcription failed: %s", audio_path)
        return None
