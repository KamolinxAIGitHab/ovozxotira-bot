import asyncio
import logging
import os
import re
import time
from typing import Optional

from openai import AsyncOpenAI

from bot.translit import latin_to_cyrillic

logger = logging.getLogger(__name__)
client = AsyncOpenAI()

TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o-mini")

# gpt-4o-mini-transcribe was faster and more accurate than gpt-4o-transcribe on
# Uzbek speech in the ReelsTahlilBot comparison (tools/stt_compare.py):
# gpt-4o-transcribe drifted into Azerbaijani/Kazakh spelling and produced endless
# repeats. No language (uz is rejected by the API) and no prompt: both made the
# results less stable. Uzbek comes back in Latin and is transliterated locally.
STT_MODEL = os.getenv("STT_MODEL", "gpt-4o-mini-transcribe")
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


async def _call(model: str, audio_path: str, lang: Optional[str], prompt: Optional[str]) -> Optional[str]:
    kwargs = {"model": model}
    if prompt:
        kwargs["prompt"] = prompt
    if lang:
        kwargs["language"] = lang
    with open(audio_path, "rb") as f:
        result = await client.audio.transcriptions.create(file=f, **kwargs)
    return (result.text or "").strip() or None


async def _transcribe_ru(audio_path: str) -> Optional[str]:
    return await _call("gpt-4o-transcribe", audio_path, "ru", PROMPT_RU)


# Seconds of speech vs. expected text: normal Uzbek speech gives ~8-14 characters
# per second. A transcript far below this means the model stopped early.
MIN_CHARS_PER_SEC = 4
MIN_SECONDS_FOR_CHECK = 10

# The same short piece repeated 10+ times in a row is a model hallucination loop.
_REPEAT_RE = re.compile(r"(.{1,8}?)\1{9,}")


def _collapse_repeats(text: str) -> str:
    return _REPEAT_RE.sub(r"\1", text)


def _looks_broken(text: Optional[str], duration: Optional[int]) -> bool:
    if not text:
        return False
    if _REPEAT_RE.search(text):
        return True
    return bool(
        duration
        and duration >= MIN_SECONDS_FOR_CHECK
        and len(text) < duration * MIN_CHARS_PER_SEC
    )


async def _transcribe_uz(audio_path: str, duration: Optional[int] = None) -> Optional[str]:
    text = await _call(STT_MODEL, audio_path, None, None)
    if _looks_broken(text, duration):
        logger.warning(
            "Suspicious transcript (%d chars, %ss audio, repeats=%s), retrying once",
            len(text), duration, bool(_REPEAT_RE.search(text)),
        )
        retry = await _call(STT_MODEL, audio_path, None, None)
        candidates = [t for t in (text, retry) if t]
        text = min(
            candidates,
            key=lambda t: (_looks_broken(t, duration), -len(_collapse_repeats(t))),
        )
    return _collapse_repeats(text) if text else text


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


async def transcribe(
    audio_path: str, mode: str = "uz_cyr", duration: Optional[int] = None
) -> Optional[str]:
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
            uz_text = await _timed(_transcribe_uz(audio_path, duration), timings, "uz")
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
            text = latin_to_cyrillic(text)
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
