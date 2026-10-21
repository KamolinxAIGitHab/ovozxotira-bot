"""Uzbek Latin -> Cyrillic transliteration (rule based, instant, no API call).

Only the script is changed. Brand names and other foreign tokens are left in
Latin: words with a capital letter inside (YouTuber, UPG, iPhone), and words
with the letters c (outside "ch") or w, which do not exist in Uzbek Latin.
"""
import re

_APOS = "'ʻʼ‘’`´"
_WORD = re.compile("[A-Za-z" + _APOS + "]+")
_EDGES = re.compile("^([" + _APOS + "]*)(.*?)([" + _APOS + "]*)$", re.S)

_SIMPLE = {
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ",
    "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о",
    "p": "п", "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в",
    "x": "х", "y": "й", "z": "з", "c": "к", "w": "в",
}


def _convert_core(low: str) -> str:
    out = []
    i, n = 0, len(low)
    while i < n:
        c = low[i]
        two = low[i:i + 2]
        if low.startswith("yo'", i):
            out.append("йў"); i += 3
        elif low.startswith("tsiya", i):
            out.append("ция"); i += 5
        elif i == 0 and two == "ts":
            out.append("ц"); i += 2
        elif two == "o'":
            out.append("ў"); i += 2
        elif two == "g'":
            out.append("ғ"); i += 2
        elif two == "sh":
            out.append("ш"); i += 2
        elif two == "ch":
            out.append("ч"); i += 2
        elif two == "yo":
            out.append("ё"); i += 2
        elif two == "yu":
            out.append("ю"); i += 2
        elif two == "ya":
            out.append("я"); i += 2
        elif i == 0 and two == "ye":
            out.append("е"); i += 2
        elif i == 0 and c == "e":
            out.append("э"); i += 1
        elif c == "'":
            out.append("ъ"); i += 1
        else:
            out.append(_SIMPLE.get(c, c)); i += 1
    return "".join(out)


def _convert_word(word: str) -> str:
    lead, core, trail = _EDGES.match(word).groups()
    if not core or not any(ch.isalpha() for ch in core):
        return word
    # Brand names / abbreviations (capital letter inside the word): keep Latin
    if any(ch.isupper() for ch in core[1:]):
        return word
    low = core.lower()
    for a in _APOS:
        low = low.replace(a, "'")
    # Letters that are not part of Uzbek Latin: foreign word, keep Latin
    if "w" in low or re.search(r"c(?!h)", low):
        return word
    result = _convert_core(low)
    if core[0].isupper() and result:
        result = result[0].upper() + result[1:]
    return lead + result + trail


def latin_to_cyrillic(text: str) -> str:
    return _WORD.sub(lambda m: _convert_word(m.group(0)), text)
