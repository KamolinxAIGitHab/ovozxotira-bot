from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import database

router = Router(name="settings")

MODES = {
    "uz_cyr": "Ўзбек (кирилл)",
    "uz_lat": "O'zbek (lotin)",
    "ru": "Русский",
}

TEXT = (
    "<b>Транскрипция тили</b>\n\n"
    "Овозли хабар қайси ёзувда матнга айлансин?\n"
    "• Ўзбек (кирилл) ёки O'zbek (lotin) — русча овоз русча матн бўлиб қолади.\n"
    "• Русский — овоз русча деб ҳисобланади.\n\n"
    "Ҳозирги танлов: <b>{current}</b>"
)


def _keyboard(current: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=("✅ " if key == current else "") + label,
            callback_data=f"lang:{key}",
        )]
        for key, label in MODES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("lang"))
async def cmd_lang(message: Message) -> None:
    if message.from_user is None:
        return
    current = await database.repository.get_lang_mode(message.from_user.id)
    await message.answer(
        TEXT.format(current=MODES[current]),
        reply_markup=_keyboard(current),
    )


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(callback: CallbackQuery) -> None:
    mode = (callback.data or "").split(":", 1)[1]
    if mode not in MODES or callback.message is None:
        await callback.answer()
        return
    await database.repository.set_lang_mode(callback.from_user.id, mode)
    await callback.message.edit_text(
        TEXT.format(current=MODES[mode]),
        reply_markup=_keyboard(mode),
    )
    await callback.answer("Сақланди")
