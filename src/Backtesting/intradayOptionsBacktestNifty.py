
#!/usr/bin/env python3
"""
BACKTEST ENGINE - NIFTY TRIGGER + ATM OPTIONS EXECUTION
=========================================================

LOGIC FLOW:
1. Signal generation based on NIFTY 5-min candles with EMA rejection.
2. On valid signal:
   - Take NIFTY trade (index) with 1:2 RR.
   - Take ATM option trade (CE/PE) with 1:2 RR.
3. Correct Zerodha-compliant expiry resolution (Weekly + Monthly, Tuesday-based).
4. Fetch ATM option candles.
5. Intraday-only simulation (no carry-forward).
6. Outputs two CSVs:
   - nifty_trades.csv
   - option_trades.csv
"""

import pandas as pd
import math
from datetime import datetime, timedelta, date
from src.zerodha_client import ZerodhaClient
from src.generateAuthToken import init_kite
from src.utils.logger import logger
import os
from dotenv import load_dotenv
from pathlib import Path

# ================= CONFIG =================

START_DATE = "2025-11-18"
END_DATE   = "2025-11-24"
TIMEFRAME  = "5minute"
NIFTY_TOKEN = 256265
RR_RATIO   = 2
QTY        = 50    # lot size multiplier if you want later

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

API_KEY    = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")

# ================= INDICATORS =================

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_angle(series, lookback=5):
    delta = series.diff(lookback)
    return (delta / lookback).apply(lambda x: math.degrees(math.atan(x)))


def atm_strike(price):
    return round(price / 50) * 50


# ================= CANDLE FILTERS (REJECTION) =================

def is_bullish_rejection(candle, ema20, ema30):
    """
    Bullish rejection:
    - Green candle
    - Body >= 10 points
    - Low close to EMA20 / EMA30 (within 5 points)
    """
    body = candle["close"] - candle["open"]
    if body < 10:
        return False
    if candle["close"] <= candle["open"]:
        return False
    # rejection from EMA
    return min(abs(candle["low"] - ema20), abs(candle["low"] - ema30)) < 5


def is_bearish_rejection(candle, ema20, ema30):
    """
    Bearish rejection:
    - Red candle
    - Body >= 10 points
    - High close to EMA20 / EMA30 (within 5 points)
    """
    body = candle["open"] - candle["close"]
    if body < 10:
        return False
    if candle["close"] >= candle["open"]:
        return False
    return min(abs(candle["high"] - ema20), abs(candle["high"] - ema30)) < 5


# ================= BACKTEST ENGINE =================

class BacktestEngine:
    def __init__(self, client):
        self.client = client
        self.nifty_df = None
        self.nifty_trades = []
        self.option_trades = []

    # ------------ MAIN LOOP ------------
    def run(self):
        self.nifty_df = self.load_nifty()

        for i in range(30, len(self.nifty_df)):
            row = self.nifty_df.iloc[i]

            # No new entries after 15:00
            if row["date"].time() >= datetime.strptime("15:00", "%H:%M").time():
                continue

            ema20 = row["ema20"]
            ema30 = row["ema30"]
            slope20 = row["slope20"]

            # LONG SETUP: Bullish trend + bullish rejection
            if (
                ema20 > ema30
                and slope20 >= 30
                and is_bullish_rejection(row, ema20, ema30)
            ):
                self.process_signal(i, "CE")

            # SHORT SETUP: Bearish trend + bearish rejection
            elif (
                ema20 < ema30
                and slope20 <= -30
                and is_bearish_rejection(row, ema20, ema30)
            ):
                self.process_signal(i, "PE")

        self.export_csvs()

    # ------------ SIGNAL PROCESS ------------
    def process_signal(self, idx, direction):
        """
        direction: 'CE' for bullish, 'PE' for bearish
        Creates:
        - NIFTY trade (index)
        - ATM Option trade
        """
        row = self.nifty_df.iloc[idx]
        atm = atm_strike(row["close"])
        signal_time = row["date"]

        # ===== NIFTY TRADE (INDEX) =====
        nifty_entry = row["close"]
        if direction == "CE":  # bullish
            sl_nifty = row["low"]
            target_nifty = nifty_entry + RR_RATIO * (nifty_entry - sl_nifty)
        else:  # PE / bearish (short NIFTY)
            sl_nifty = row["high"]
            target_nifty = nifty_entry - RR_RATIO * (sl_nifty - nifty_entry)

        nifty_outcome, nifty_exit = self.simulate_nifty_trade(
            start_index=idx,
            entry=nifty_entry,
            sl=sl_nifty,
            target=target_nifty,
            direction=direction,
        )

        if direction == "CE":
            nifty_pnl = nifty_exit - nifty_entry
        else:
            nifty_pnl = nifty_entry - nifty_exit

        self.nifty_trades.append(
            {
                "Time": signal_time,
                "Direction": "LONG" if direction == "CE" else "SHORT",
                "NIFTY_Entry": nifty_entry,
                "NIFTY_SL": sl_nifty,
                "NIFTY_Target": target_nifty,
                "NIFTY_Exit": nifty_exit,
                "NIFTY_Outcome": nifty_outcome,
                "NIFTY_PnL": nifty_pnl,
                "ATM_Strike": atm,
            }
        )

        # ===== OPTION TRADE (ATM CE/PE) =====
        option_df = self.fetch_option_data(signal_time, atm, direction)
        if option_df.empty:
            return  # no option data, skip option leg

        opt_row = option_df.iloc[0]
        opt_entry = opt_row["close"]
        opt_sl = opt_row["low"]
        opt_target = opt_entry + RR_RATIO * (opt_entry - opt_sl)

        opt_outcome, opt_exit = self.simulate_option_trade(
            option_df, opt_entry, opt_sl, opt_target, direction
        )

        opt_pnl = opt_exit - opt_entry

        '''
        if direction == "CE":
            opt_sl = opt_row["low"]
            opt_target = opt_entry + RR_RATIO * (opt_entry - opt_sl)
        else:
            opt_sl = opt_row["high"]
            opt_target = opt_entry - RR_RATIO * (opt_sl - opt_entry)

        opt_outcome, opt_exit = self.simulate_option_trade(
            option_df, opt_entry, opt_sl, opt_target, direction
        )

        if direction == "CE":
            opt_pnl = opt_exit - opt_entry
        else:
            opt_pnl = opt_entry - opt_exit
        '''
        self.option_trades.append(
            {
                "Time": opt_row["date"],
                "Strike": atm,
                "Direction": direction,
                "Entry": opt_entry,
                "SL": opt_sl,
                "Target": opt_target,
                "Exit": opt_exit,
                "Outcome": opt_outcome,
                "PnL": opt_pnl,
            }
        )

    # ------------ EXPIRY CODE HANDLER (SEBI COMPLIANT, TUESDAY) ------------
    def get_expiry_code(self, trade_date: date):
        """
        SEBI-compliant expiry generator for NIFTY (Tuesday-based).

        Monthly Expiry : LAST TUESDAY of the month -> YYMMM (25NOV)
        Weekly Expiry  : Other Tuesdays            -> YYMDD (25N11, 25D02)
        """
        d = trade_date
        # find next Tuesday
        while d.weekday() != 1:  # Tuesday = 1
            d += timedelta(days=1)

        # last day of this month
        next_month = d.replace(day=28) + timedelta(days=4)
        last_day = next_month.replace(day=1) - timedelta(days=1)

        # last Tuesday of this month
        last_tuesday = last_day
        while last_tuesday.weekday() != 1:
            last_tuesday -= timedelta(days=1)

        is_monthly = (d == last_tuesday)

        year = d.strftime("%y")
        day = d.strftime("%d")
        month = d.month

        if is_monthly:
            return f"{year}{d.strftime('%b').upper()}"

        month_code_map = {
            1: "0",
            2: "1",
            3: "2",
            4: "3",
            5: "4",
            6: "5",
            7: "6",
            8: "7",
            9: "8",
            10: "O",
            11: "N",
            12: "D",
        }
        return f"{year}{month_code_map[month]}{day}"

    # ------------ TOKEN RESOLVER ------------
    def resolve_instrument_token(self, tradingsymbol, exchange="NFO"):
        for ins in self.client.kite.instruments(exchange):
            if ins["tradingsymbol"] == tradingsymbol:
                return ins["instrument_token"]
        return None

    # ------------ FETCH OPTION DATA ------------
    def fetch_option_data(self, time, strike, direction):
        # normalise time to naive
        if hasattr(time, "tzinfo") and time.tzinfo is not None:
            time = time.replace(tzinfo=None)

        expiry_code = self.get_expiry_code(time.date())
        symbol = f"NIFTY{expiry_code}{strike}{direction}"

        token = self.resolve_instrument_token(symbol)
        if not token:
            logger.warning(f"Instrument not found: {symbol}")
            return pd.DataFrame()

        start = time
        end = time + timedelta(hours=4)

        data = self.client.get_historical_candles(token, start, end, TIMEFRAME)
        df = pd.DataFrame(data)
        # normalise tz
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

        return df[df["date"] >= start]

    # ------------ NIFTY TRADE SIMULATION (INDEX) ------------
    def simulate_nifty_trade(self, start_index, entry, sl, target, direction):
        """
        Simulate NIFTY intraday from start_index to end of SAME DAY.
        direction: 'CE' for bullish (long), 'PE' for bearish (short)
        """
        entry_date = self.nifty_df.iloc[start_index]["date"].date()

        for j in range(start_index + 1, len(self.nifty_df)):
            candle = self.nifty_df.iloc[j]
            c_date = candle["date"].date()

            # new day -> EOD exit at previous close
            if c_date != entry_date:
                prev = self.nifty_df.iloc[j - 1]
                return "EOD_EXIT", prev["close"]

            if direction == "CE":  # long
                if candle["high"] >= target:
                    return "TARGET_HIT", target
                if candle["low"] <= sl:
                    return "SL_HIT", sl
            else:  # PE -> short
                if candle["low"] <= target:
                    return "TARGET_HIT", target
                if candle["high"] >= sl:
                    return "SL_HIT", sl

        return "EOD_EXIT", self.nifty_df.iloc[-1]["close"]

    # ------------ OPTION TRADE SIMULATION ------------
    def simulate_option_trade(self, df, entry, sl, target, direction):
        """
        Start simulation from NEXT candle after entry candle
        """
        for i in range(1, len(df)):  # 🔥 start from 2nd candle
            candle = df.iloc[i]

            if direction == "CE":
                # Target first check is more realistic for momentum trades
                if candle["high"] >= target:
                    return "TARGET_HIT", target
                if candle["low"] <= sl:
                    return "SL_HIT", sl
            else:
                if candle["low"] <= target:
                    return "TARGET_HIT", target
                if candle["high"] >= sl:
                    return "SL_HIT", sl

        return "EOD_EXIT", df.iloc[-1]["close"]

    # ------------ LOAD NIFTY DATA ------------
    def load_nifty(self):
        start = datetime.strptime(START_DATE, "%Y-%m-%d")
        end   = datetime.strptime(END_DATE, "%Y-%m-%d")
        data = self.client.get_historical_candles(NIFTY_TOKEN, start, end, TIMEFRAME)
        df = pd.DataFrame(data)
        df["ema20"]   = ema(df["close"], 15)
        df["ema30"]   = ema(df["close"], 21)
        df["slope20"] = calculate_angle(df["ema20"])
        return df

    # ------------ EXPORT CSV ------------

    def export_csvs(self):
        pd.DataFrame(self.nifty_trades).to_csv("nifty_trades.csv", index=False)
        pd.DataFrame(self.option_trades).to_csv("option_trades.csv", index=False)
        logger.success("✅ CSVs generated: nifty_trades.csv, option_trades.csv")


# ================= MAIN =================

def main():
    kite = init_kite(API_KEY, API_SECRET)
    client = ZerodhaClient(kite)
    engine = BacktestEngine(client)
    engine.run()


if __name__ == "__main__":
    main()
