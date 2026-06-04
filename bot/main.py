import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import BOT_TOKEN, SUMMARY_HOUR, SUMMARY_MINUTE, VOICE_DIR, SUMMARIES_DIR
from bot.database.repository import init_db
from bot.handlers import commands, voice, export
from bot.services.summary_service import generate_daily_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    os.makedirs(VOICE_DIR, exist_ok=True)
    os.makedirs(SUMMARIES_DIR, exist_ok=True)

    await init_db()
    logger.info("Database initialised")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(commands.router)
    dp.include_router(voice.router)
    dp.include_router(export.router)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        generate_daily_summary,
        trigger="cron",
        hour=SUMMARY_HOUR,
        minute=SUMMARY_MINUTE,
        kwargs={"bot": bot},
        id="daily_summary",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started - daily summaries at %02d:%02d UTC", SUMMARY_HOUR, SUMMARY_MINUTE)

    logger.info("Bot polling started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())