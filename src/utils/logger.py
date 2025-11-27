# src/utils/logger.py
from loguru import logger
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "bot.log"

# Configure loguru
logger.add(
    LOG_FILE,
    rotation="1 MB",
    retention="7 days",
    compression="zip",
    enqueue=True,
    backtrace=True,
    diagnose=True,
)

__all__ = ["logger"]
