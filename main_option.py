# main.py
from src.zerodha_client import ZerodhaClient
from src.utils.logger import logger
from src.generateAuthToken import init_kite
from src.strategies.nifty_ema_rejection_options import NiftyEMARejectionStrategyOptions

from pathlib import Path
from dotenv import load_dotenv
import os

# Load .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE_PATH)


def main():
    logger.info("Starting Zerodha trading project (test run)...")

    API_KEY = os.getenv("KITE_API_KEY")
    API_SECRET = os.getenv("KITE_API_SECRET")
    print("API_KEY: ",API_KEY)
    print("API_SECRET: ", API_SECRET)
    if not API_KEY or not API_SECRET:
        logger.error("API Key or Secret missing in .env file")
        return

    try:
        # ✅ Authenticate and get Kite session
        kite = init_kite(API_KEY, API_SECRET)
        # ✅ Pass authenticated kite to client
        client = ZerodhaClient(kite)
        # 1) Test profile API
        profile = client.get_profile()
        print("Logged in as:", profile.get("user_name"), "| User ID:", profile.get("user_id"))


        # 2) Test LTP for NIFTY 50 index
        nifty_symbol = "NSE:NIFTY 50"
        ltp = client.get_ltp(nifty_symbol)
        print(f"LTP for {nifty_symbol} is {ltp}")


        # 3) Show current positions (if any)
        positions = client.get_positions()
        print("Current positions:")
        print(positions)

        # 3) Strategy instance
        strategy = NiftyEMARejectionStrategyOptions(kite, client)

        # 4) Run strategy loop
        strategy.run()

        logger.success("run completed successfully.")

    except Exception as e:
        logger.error(f"Error during test run: {str(e)}")

if __name__ == "__main__":
    main()
