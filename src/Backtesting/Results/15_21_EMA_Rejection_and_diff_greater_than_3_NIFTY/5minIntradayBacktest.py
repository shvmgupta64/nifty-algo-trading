"""
BACKTEST ENGINE FOR NIFTY EMA REJECTION STRATEGY
==================================================
This script backtests the same live strategy but on historical data and exports
detailed trade logs to CSV for analysis.

- Uses 5-min candles
- EMA 20 & EMA 30
- 30-degree slope approximation
- Rejection candle logic
- RR 1:2
- Outputs CSV trade journal

HOW TO USE:
1. Ensure Zerodha KiteConnect is authenticated
2. Update START_DATE and END_DATE
3. Run: python backtest.py
4. Output CSV: backtest_results.csv
"""

import pandas as pd
import math
from datetime import datetime, timedelta
from src.zerodha_client import ZerodhaClient
from src.generateAuthToken import init_kite
from src.utils.logger import logger
import os
from dotenv import load_dotenv
from pathlib import Path

# ========== CONFIGURATION ==========
START_DATE = "2024-12-01"
END_DATE = "2025-02-28"
TIMEFRAME = "5minute"
NIFTY_TOKEN = 256265
QTY = 50
RR_RATIO = 1.9

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")


# ========== INDICATORS ==========

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_angle(series, lookback=5):
    delta = series.diff(lookback)
    angle = (delta / lookback).apply(lambda x: math.degrees(math.atan(x)))
    return angle


# ========== CANDLE FILTERS ==========
def is_bullish_rejection(candle, ema15, ema21):

    if (ema15 < ema21):
        return False

    o = candle["open"]
    c = candle["close"]
    h = candle["high"]
    l = candle["low"]

    body = c - o
    lower_wick = o - l
    upper_wick = h - c

    low_in_ema_zone = (
            abs(candle["low"] - ema15) <= 7 or
            abs(candle["low"] - ema21) <= 7
    )

    open_in_ema_zone = (
            abs(candle["open"] - ema15) <= 7 or
            abs(candle["open"] - ema21) <= 7
    )
    # Must interact with EMA zone

    wick_rejection = (
        (upper_wick < 4
         and lower_wick >= 10
         and c > o
         and open_in_ema_zone)
        or
        (o > ema15
         and c > o
         and l < ema21
         and upper_wick < 4
         and lower_wick >= 10)
    )
    body_rejection = body >= 10 and upper_wick <= body * 0.3 and low_in_ema_zone

    return wick_rejection or body_rejection


def is_bearish_rejection(candle, ema15, ema21) :
    if (ema15 > ema21):
        return False
    o = candle["open"]
    c = candle["close"]
    h = candle["high"]
    l = candle["low"]

    body = o - c
    upper_wick = h - o
    lower_wick = c - l

    high_in_ema_zone = (
            abs(candle["high"] - ema15) <= 4 or
            abs(candle["high"] - ema21) <= 4
    )

    open_in_ema_zone = (
            abs(candle["open"] - ema15) <= 4 or
            abs(candle["open"] - ema21) <= 4
    )

    wick_rejection = (
            (lower_wick < 4
             and upper_wick >= 10
             and o > c
             and open_in_ema_zone)
            or
            (o < ema15
             and o > c
             and h > ema21
             and lower_wick < 4
             and upper_wick >= 10)
    )

    # Body-based bearish rejection
    body_rejection = body >= 10 and lower_wick <= body * 0.3 and high_in_ema_zone

    return wick_rejection or body_rejection
'''
def is_bullish_rejection(candle, ema20, ema30):
    body = candle['close'] - candle['open']
    return body >= 10 and candle['open'] < candle['close'] and min(abs(candle['low'] - ema20),
                                                                   abs(candle['low'] - ema30)) < 5


def is_bearish_rejection(candle, ema20, ema30):
    body = candle['open'] - candle['close']
    return body >= 10 and candle['open'] > candle['close'] and min(abs(candle['high'] - ema20),
                                                                   abs(candle['high'] - ema30)) < 5
'''

def atm_strike(price):
    return round(price / 50) * 50


# ========== BACKTEST ENGINE ==========
class BacktestEngine:
    def __init__(self, client):
        self.client = client
        self.trades = []

    def run(self):
        logger.info("Starting backtest...")

        candles = self.fetch_data()
        df = pd.DataFrame(candles)
        df['ema20'] = ema(df['close'], 15)
        df['ema30'] = ema(df['close'], 21)
        df['slope20'] = calculate_angle(df['ema20'])

        daily_sl_count = {}
        current_day = None
        active_trade_until = None


        for i in range(30, len(df)):
            row = df.iloc[i]

            trade_day = row['date'].date()

            # Reset when day changes
            if current_day != trade_day:
                current_day = trade_day
                daily_sl_count[current_day] = 0


            # If 2 SL already hit for the day, skip further trades
            if daily_sl_count[current_day] >= 2:
                continue
            prev = df.iloc[i - 1]

            if row['date'].time() >= datetime.strptime("15:00", "%H:%M").time():
                continue

            if active_trade_until and row['date'] < active_trade_until:
                continue

            print(row)
            if row['ema20'] > row['ema30']  and abs(row['ema20'] - row['ema30']) >= 3 and is_bullish_rejection(row, row['ema20'],
                                                                                             row['ema30']):
            #if row['ema20'] > row['ema30'] and is_bullish_rejection(row, row['ema20'], row['ema30']):

                entry = row['close']
                sl = row['low']

                target = entry + RR_RATIO * (entry - sl)
                outcome, exit_price, exit_time = self.simulate_trade(df, i, entry, sl, target, direction="CE")
                self.trades.append(self.log_trade(row['date'], exit_time, "CE", entry, sl, target, outcome, exit_price))
                active_trade_until = exit_time
                if outcome == "SL_HIT":
                    daily_sl_count[current_day] += 1

            elif row['ema20'] < row['ema30']  and abs(row['ema20'] - row['ema30']) >= 3 and is_bearish_rejection(row, row['ema20'],
                                                                                                row['ema30']):
            #elif row['ema20'] < row['ema30'] and is_bearish_rejection(row, row['ema20'], row['ema30']):

                entry = row['close']
                sl = row['high']
                target = entry - RR_RATIO * (sl - entry)
                outcome, exit_price, exit_time = self.simulate_trade(df, i, entry, sl, target, direction="PE")
                self.trades.append(self.log_trade(row['date'], exit_time, "PE", entry, sl, target, outcome, exit_price))
                active_trade_until = exit_time
                if outcome == "SL_HIT":
                    daily_sl_count[current_day] += 1

        self.export_csv()

    def simulate_trade(self, df, entry_index, entry, sl, target, direction):
        """
        Intraday trade simulation.
        Trade will be force-closed at the last candle of the SAME DAY (no carry forward).
        Returns: ("TARGET_HIT" / "SL_HIT" / "EOD_EXIT", exit_price)
        """
        entry_date = df.iloc[entry_index]['date'].date()
        '''
        for j in range(entry_index + 1, len(df)):
            candle = df.iloc[j]
            candle_date = candle['date'].date()

            # If next day starts, force exit at previous candle close
            if candle_date != entry_date:
                prev_candle = df.iloc[j - 1]
                return "EOD_EXIT", prev_candle['close']

            if direction == "CE":
                if candle['high'] >= target:
                    return "TARGET_HIT", target
                if candle['low'] <= sl:
                    return "SL_HIT", sl
            else:  # PE buy
                if candle['low'] <= target:
                    return "TARGET_HIT", target
                if candle['high'] >= sl:
                    return "SL_HIT", sl
        '''
        for j in range(entry_index + 1, len(df)):
            candle = df.iloc[j]
            candle_date = candle['date'].date()

            # If next day starts, force exit at previous candle
            if candle_date != entry_date:
                prev_candle = df.iloc[j - 1]
                return "EOD_EXIT", prev_candle['close'], prev_candle['date']

            if direction == "CE":
                if candle['high'] >= target:
                    return "TARGET_HIT", target, candle['date']
                if candle['low'] <= sl:
                    return "SL_HIT", sl, candle['date']

            else:  # PE
                if candle['low'] <= target:
                    return "TARGET_HIT", target, candle['date']
                if candle['high'] >= sl:
                    return "SL_HIT", sl, candle['date']

        last = df.iloc[-1]
        return "EOD_EXIT", last['close'], last['date']

    '''
    def log_trade(self, time, direction, entry, sl, target, outcome, exit_price):
        if direction == "CE":
            if outcome == "TARGET_HIT":
                pnl = target - entry
            elif outcome == "SL_HIT":
                pnl = sl - entry
            else:  # EOD_EXIT
                pnl = exit_price-entry
        else:
            if outcome == "TARGET_HIT":
                pnl = entry - target
            elif outcome == "SL_HIT":
                pnl = entry - sl
            else:  # EOD_EXIT
                pnl = entry - exit_price
        return {
            "Time": time,
            "Direction": direction,
            "Entry": entry,
            "StopLoss": sl,
            "Target": target,
            "ExitPrice": exit_price,
            "Outcome": outcome,
            "Risk": abs(entry - sl),
            "Reward": abs(target - entry),
            "PnL": pnl
        }
    '''

    def log_trade(self, entry_time, exit_time, direction, entry, sl, target, outcome, exit_price):
        if direction == "CE":
            pnl = exit_price - entry
        else:
            pnl = entry - exit_price

        return {
            "EntryTime": entry_time,
            "ExitTime": exit_time,
            "Direction": direction,
            "Entry": entry,
            "StopLoss": sl,
            "Target": target,
            "ExitPrice": exit_price,
            "Outcome": outcome,
            "Risk": abs(entry - sl),
            "Reward": abs(target - entry),
            "PnL": pnl
        }

    def export_csv(self):
        df = pd.DataFrame(self.trades)
        df.to_csv("backtest_results.csv", index=False)
        logger.success("✅ Backtest CSV generated: backtest_results.csv")

    def fetch_data(self):
        start = datetime.strptime(START_DATE, "%Y-%m-%d")
        end = datetime.strptime(END_DATE, "%Y-%m-%d")
        return self.client.get_historical_candles(NIFTY_TOKEN, start, end, TIMEFRAME)


# ========== MAIN ==========


def main():
    kite = init_kite(API_KEY, API_SECRET)
    client = ZerodhaClient(kite)

    engine = BacktestEngine(client)
    engine.run()


if __name__ == '__main__':
    main()
