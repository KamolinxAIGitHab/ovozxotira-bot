import asyncio
import logging
import os
import re
import time
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
client = AsyncOpenAI()

TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o-mini")

PROMPT_UZ = (
    "Bu o'zbek tilidagi suhbat. "
    "Ucell, Uztelekom, Uzonline, internet, bank, shartnoma, xarid."
)
# Cyrillic prompt makes gpt-4o-transcribe answer in Cyrillic directly, so the
# extra script-conversion call is usually not needed in uz_cyr mode.
PROMPT_UZ_CYR = "Бу ўзбек тилидаги суҳбат. Ucell, Uztelekom, Uzonline, интернет, банк, шартнома, харид."
PROMPT_RU = "Это разговор на русском языке."

# Letters/sequences that occur only in Uzbek, never in Russian speech. When the
# Uzbek transcript contains one, there is no need to wait for language detection.
_UZ_CYR_MARKERS = re.compile(r"[ЎўҚқҒғҲҳ]")
_UZ_LAT_MARKERS = re.compile(r"[oOgG][ʻʼ'’`‘]")

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


def _is_certainly_uzbek(text: Optional[str]) -> bool:
    return bool(text) and bool(_UZ_CYR_MARKERS.search(text) or _UZ_LAT_MARKERS.search(text))


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


async def _transcribe_uz(audio_path: str, mode: str = "uz_cyr") -> Optional[str]:
    # Both whisper-1 and gpt-4o-transcribe reject language="uz" (HTTP 400), so
    # a request with it only wastes about a second before any fallback. Go
    # straight to gpt-4o-transcribe without a language hint.
    prompt = PROMPT_UZ_CYR if mode == "uz_cyr" else PROMPT_UZ
    return await _call("gpt-4o-transcribe", audio_path, None, prompt)


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


async def _timed(coro, timings: dict, key: str):
    t0 = time.monotonic()
    try:
        return await coro
    finally:
        timings[key] = time.monotonic() - t0


async def transcribe(audio_path: str, mode: str = "uz_cyr") -> Optional[str]:
    """mode: 'uz_cyr' | 'uz_lat' | 'ru'.

    Language detection and the Uzbek transcription run in parallel (faster).
    Russian speech is always transcribed as Russian. Uzbek speech is returned
    in Cyrillic or Latin script (uz_cyr / uz_lat), or translated into Russian
    (ru).
    """
    t_start = time.monotonic()
    timings: dict[str, float] = {}
    try:
        detect_task = asyncio.ensure_future(
            _timed(_detect_language(audio_path), timings, "detect")
        )
        try:
            uz_text = await _timed(_transcribe_uz(audio_path, mode), timings, "uz")
        except Exception as exc:  # handled below
            uz_text = exc

        if isinstance(uz_text, str) and _is_certainly_uzbek(uz_text):
            # Uzbek-only letters found: skip waiting for (slow, variable) detection.
            detect_task.cancel()
            lang = "uz"
        else:
            try:
                lang = await detect_task
            except Exception:
                lang = "uz"
        if lang == "ru":
            return await _timed(_transcribe_ru(audio_path), timings, "ru")
        if isinstance(uz_text, BaseException):
            logger.error("Uzbek transcription failed: %r", uz_text)
            return None
        text = uz_text
        if not text:
            return None
        if mode == "ru":
            return await _timed(_translate_to_russian(text), timings, "translate")

        cyr, lat = _script_counts(text)
        if mode == "uz_cyr" and lat > cyr:
            text = await _timed(_convert_script(text, "cyrillic"), timings, "convert")
        elif mode == "uz_lat" and cyr > lat:
            text = await _timed(_convert_script(text, "latin"), timings, "convert")
        return text
    except Exception:
        logger.exception("Transcription failed: %s", audio_path)
        return None
    finally:
        logger.info(
            "Transcription stages: %s, total=%.1fs",
            ", ".join(f"{k}={v:.1f}s" for k, v in timings.items()),
            time.monotonic() - t_start,
        )
