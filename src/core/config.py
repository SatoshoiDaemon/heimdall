import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "modbot_db")
    REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379/0")
    CAPTCHA_TIMEOUT_SECONDS = int(os.getenv("CAPTCHA_TIMEOUT_SECONDS", "300"))
    LOG_WORKER_INTERVAL_SECONDS = int(os.getenv("LOG_WORKER_INTERVAL_SECONDS", "5"))

config = Config()
