from aiogram.types import Message

MAX_LEN = 3900  # Telegram чегараси 4096


def chunk_text(text: str, max_len: int = MAX_LEN) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for line in text.split("\n"):
        while len(line) > max_len:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:max_len])
            line = line[max_len:]
        if cur and len(cur) + len(line) + 1 > max_len:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks or [""]


async def answer_long(message: Message, text: str) -> None:
    for part in chunk_text(text):
        await message.answer(part)
