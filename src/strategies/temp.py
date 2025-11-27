# src/strategies/nifty_ema_rejection_futures.py
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import pytz
from kiteconnect import KiteConnect
from src.zerodha_client import ZerodhaClient
from src.utils.indicators import ema, ema_angle_is_up, ema_angle_is_down
from src.utils.candle_utils import (
    is_bullish_rejection_candle,
    is_bearish_rejection_candle,
)
from src.utils.order_manager import OrderManager
from src.utils.logger import logger

IST = pytz.timezone("Asia/Kolkata")

NIFTY_UNDERLYING_TOKEN = 256265
NIFTY_FUT_SYMBOL = "NIFTY25NOVFUT"  # ⚠️ update with current active futures symbol

ENTRY_END_TIME = datetime.strptime("15:00:00", "%H:%M:%S").time()
FORCE_EXIT_TIME = datetime.strptime("15:15:00", "%H:%M:%S").time()


class NiftyEMARejectionStrategy:
    def __init__(self, kite: KiteConnect, client: ZerodhaClient):
        self.kite = kite
        self.client = client
        self.order_manager = OrderManager(client, kite)

        self.last_signal_candle_time: Optional[datetime] = None
        self.last_processed_candle_time: Optional[datetime] = None

        self.quantity = 0  # set your lot size here (e.g. 50)

        self.cached_closes = []
        self.ema20_cache = []
        self.ema30_cache = []

    # ================= MAIN LOOP =================

    def run(self):
        logger.info("Starting NIFTY FUTURES EMA Rejection Strategy...")

        while True:
            now = datetime.now(IST).time()

            if now >= FORCE_EXIT_TIME:
                self.order_manager.force_square_off_all()
                logger.info("Force exit done. Stopping strategy.")
                break

            candles = self._fetch_recent_candles()

            if candles:
                self._process_candles(candles, now)

            self.order_manager.monitor_trades()

            import time
            time.sleep(300)

    # ================= DATA FETCH =================

    def _fetch_recent_candles(self) -> Optional[List[Dict]]:
        now = datetime.now(IST)
        from_dt = (now - timedelta(days=1)).replace(hour=9, minute=15, second=0)

        try:
            return self.client.get_historical_candles(
                instrument_token=NIFTY_UNDERLYING_TOKEN,
                from_dt=from_dt,
                to_dt=now,
                interval="5minute",
            )
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            return None

    # ================= EMA CACHE =================

    def _update_ema_cache(self, closes: List[float]):
        if not self.cached_closes:
            self.cached_closes = closes
            self.ema20_cache = ema(closes, 20)
            self.ema30_cache = ema(closes, 30)
            return

        new_closes = closes[len(self.cached_closes):]
        for price in new_closes:
            self.ema20_cache.append((price * 2 / 21) + self.ema20_cache[-1] * (1 - 2 / 21))
            self.ema30_cache.append((price * 2 / 31) + self.ema30_cache[-1] * (1 - 2 / 31))
        self.cached_closes = closes

    # ================= PROCESS =================

    def _process_candles(self, candles: List[Dict], now_time):

        closes = [c["close"] for c in candles]
        self._update_ema_cache(closes)

        if len(self.ema20_cache) < 35:
            return

        last_candle = candles[-1]
        prev_candle = candles[-2]
        last_time = last_candle["date"].astimezone(IST)

        #if self.last_processed_candle_time == last_time and self.order_manager.trades:
        #    return

        self.last_processed_candle_time = last_time

        ema20_last = self.ema20_cache[-1]
        ema30_last = self.ema30_cache[-1]

        uptrend = ema20_last > ema30_last and ema_angle_is_up(self.ema20_cache)
        downtrend = ema20_last < ema30_last and ema_angle_is_down(self.ema20_cache)

        if now_time >= ENTRY_END_TIME:
            return

        logger.info(self.last_processed_candle_time)
        logger.info(self.last_signal_candle_time)
        if self.last_signal_candle_time and last_time <= self.last_signal_candle_time:
            return

        logger.info(f"""
                ✅ New Candle Processed @ {last_time}
                Close: {last_candle['close']}
                EMA20: {ema20_last:.2f}
                EMA30: {ema30_last:.2f}
                Trend: {"UP" if uptrend else "DOWN" if downtrend else "SIDEWAYS"}
                isBullishRejection: {self.is_bullish_rejection(last_candle, ema20_last, ema30_last)}
                isBearishRejection: {self.is_bearish_rejection(last_candle, ema20_last, ema30_last)}
                """)

        if uptrend and self.is_bullish_rejection(last_candle, ema20_last, ema30_last):
            logger.info("✅ LONG FUTURES ENTRY SIGNAL")
            self._enter_long_fut(last_candle, prev_candle)
            self.last_signal_candle_time = last_time

        if downtrend and self.is_bearish_rejection(last_candle, ema20_last, ema30_last):
            logger.info("✅ SHORT FUTURES ENTRY SIGNAL")
            self._enter_short_fut(last_candle, prev_candle)
            self.last_signal_candle_time = last_time

    # ================= FUTURES ENTRY =================

    def _calculate_sl(self, signal_candle, prev_candle):
        signal_low = signal_candle["low"]
        prev_low = prev_candle["low"]

        # Your exact SL rule
        if prev_low < signal_low:
            return prev_low
        return signal_low

    def _enter_long_fut(self, signal_candle: Dict, prev_candle: Dict):
        entry_price = signal_candle["close"]
        stop_loss = self._calculate_sl(signal_candle, prev_candle)
        target = entry_price + 2 * (entry_price - stop_loss)

        self.order_manager.enter_trade(
            symbol=NIFTY_FUT_SYMBOL,
            qty=self.quantity,
            direction="LONG",
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target
        )

    def _enter_short_fut(self, signal_candle: Dict, prev_candle: Dict):
        entry_price = signal_candle["close"]

        # For short, SL should be HIGH logically, but respecting your low-based rule
        stop_loss = self._calculate_sl(signal_candle, prev_candle)
        target = entry_price - 2 * (stop_loss - entry_price)

        self.order_manager.enter_trade(
            symbol=NIFTY_FUT_SYMBOL,
            qty=self.quantity,
            direction="SHORT",
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target
        )

    def is_bullish_rejection(self, candle, ema20, ema30):
        body = candle['close'] - candle['open']
        return body >= 10 and candle['open'] < candle['close'] and min(abs(candle['low'] - ema20),
                                                                       abs(candle['low'] - ema30)) < 5

    def is_bearish_rejection(self, candle, ema20, ema30):
        body = candle['open'] - candle['close']
        return body >= 10 and candle['open'] > candle['close'] and min(abs(candle['high'] - ema20),
                                                                       abs(candle['high'] - ema30)) < 5