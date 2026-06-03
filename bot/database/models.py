CREATE_VOICE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS voice_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    username        TEXT,
    first_name      TEXT,
    file_id         TEXT NOT NULL,
    file_unique_id  TEXT NOT NULL UNIQUE,
    duration        INTEGER,
    file_size       INTEGER,
    local_path      TEXT,
    transcript      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_DAILY_SUMMARIES_TABLE = """
CREATE TABLE IF NOT EXISTS daily_summaries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    summary_date    DATE NOT NULL,
    message_count   INTEGER NOT NULL,
    total_duration  INTEGER NOT NULL DEFAULT 0,
    summary_text    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, summary_date)
)
"""

# Run after CREATE TABLE in case the DB already exists without this column
MIGRATE_ADD_TRANSCRIPT = """
ALTER TABLE voice_messages ADD COLUMN transcript TEXT
"""
