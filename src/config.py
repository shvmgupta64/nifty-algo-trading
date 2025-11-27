# src/config.py
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

class Config:
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_API_SECRET: str = os.getenv("KITE_API_SECRET", "")
    KITE_ACCESS_TOKEN: str = os.getenv("KITE_ACCESS_TOKEN", "")

    # You can add defaults for strategy later
    # e.g. DEFAULT_SYMBOL = "NIFTY 50" etc.

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.KITE_API_KEY:
            missing.append("KITE_API_KEY")
        if not cls.KITE_API_SECRET:
            missing.append("KITE_API_SECRET")
        if not cls.KITE_ACCESS_TOKEN:
            missing.append("KITE_ACCESS_TOKEN")

        if missing:
            raise RuntimeError(
                f"Missing required env variables: {', '.join(missing)}. "
                f"Check your .env file."
            )
