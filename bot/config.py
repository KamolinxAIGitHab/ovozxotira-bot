import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
SUMMARY_HOUR: int = int(os.getenv("SUMMARY_HOUR", "20"))
SUMMARY_MINUTE: int = int(os.getenv("SUMMARY_MINUTE", "0"))

WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
VOICE_DIR = os.path.join(DATA_DIR, "voice_messages")
SUMMARIES_DIR = os.path.join(DATA_DIR, "summaries")
DB_PATH = os.path.join(DATA_DIR, "bot.db")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set. Copy .env.example to .env and fill in the values.")
