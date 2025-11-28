# src/strategies/nifty_ema_rejection.py
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import pytz
from kiteconnect import KiteConnect
from src.zerodha_client import ZerodhaClient
from src.utils.indicators import ema, ema_angle_is_up, ema_angle_is_down
from src.utils.getOptionTradingSymbol import (get_nifty_option_symbol,
                                              get_instrument_token)
from src.utils.candle_utils import (
    is_bullish_rejection_candle,
    is_bearish_rejection_candle,
    get_ce_strike_for_long,
    get_pe_strike_for_short,
)
from src.utils.order_manager import OrderManager
from src.utils.logger import logger

IST = pytz.timezone("Asia/Kolkata")

# NOTE: NIFTY 50 underlying token is commonly 256265, but verify from instruments dump.
NIFTY_UNDERLYING_TOKEN = 256265

ENTRY_END_TIME = datetime.strptime("15:00:00", "%H:%M:%S").time()
FORCE_EXIT_TIME = datetime.strptime("15:15:00", "%H:%M:%S").time()


class NiftyEMARejectionStrategyOptions:
    def __init__(self, kite: KiteConnect, client: ZerodhaClient):
        self.kite = kite
        self.client = client
        self.order_manager = OrderManager(client, kite)

        self.last_signal_candle_time: Optional[datetime] = None
        self.last_processed_candle_time: Optional[datetime] = None

        self.quantity = 75

        # ✅ Risk control counters
        self.sl_count_today = 0
        self.current_trade_active = False

        # EMA cache
        self.cached_closes = []
        self.ema15_cache = []
        self.ema21_cache = []
        self.processed_closed_trades = set()

    # ================= MAIN LOOP =================

    def run(self):
        logger.info("Starting NIFTY EMA Rejection Strategy (Optimized)...")

        while True:
            now = datetime.now(IST)

            # ✅ Do not process candles before 9:15 AM
            if now.time() < datetime.strptime("09:15:00", "%H:%M:%S").time():
                import time
                time.sleep(5)
                continue

            if now.time() >= FORCE_EXIT_TIME:
                self.order_manager.force_square_off_all()
                logger.info("Force exit done. Stopping strategy for the day.")
                break

            candles = self._fetch_recent_candles(NIFTY_UNDERLYING_TOKEN)

            if candles:
                self._process_candles(candles, now)

            self.order_manager.monitor_buy_option_trades()

            # ✅ Reset logic after trade closes
            for trade in self.order_manager.trades:
                # identify trade uniquely
                trade_id = id(trade)

                if trade.status != "OPEN" and trade_id not in self.processed_closed_trades:
                    self.processed_closed_trades.add(trade_id)

                    if trade.status == "SL_HIT":
                        self.sl_count_today += 1
                        logger.warning(f"❗ Stoploss hit count today: {self.sl_count_today}")

                    self.current_trade_active = False
                    self.last_signal_candle_time = None

            import time
            time.sleep(5)

    # ================= DATA FETCH =================

    def _fetch_recent_candles(self, UNDERLYING_TOKEN):
        now = datetime.now(IST)
        from_dt = (now - timedelta(days=1)).replace(hour=9, minute=15, second=0)

        try:
            return self.client.get_historical_candles(
                instrument_token=UNDERLYING_TOKEN,
                from_dt=from_dt,
                to_dt=now,
                interval="5minute",
            )
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            return None

    # ================= EMA CACHING ENGINE =================

    def _update_ema_cache(self, closes: List[float]):
        if not self.cached_closes:
            # Initial warmup
            self.cached_closes = closes
            self.ema15_cache = ema(closes, 15)
            self.ema21_cache = ema(closes, 21)
            return

        # Only process newly added candle
        new_closes = closes[len(self.cached_closes):]
        for price in new_closes:
            self.ema15_cache.append((price * 2 / 16) + self.ema15_cache[-1] * (1 - 2 / 16))
            self.ema21_cache.append((price * 2 / 22) + self.ema21_cache[-1] * (1 - 2 / 22))
        self.cached_closes = closes

    # ================= PROCESS LOGIC =================

    def _process_candles(self, candles: List[Dict], now: datetime):

        closes = [c["close"] for c in candles]
        self._update_ema_cache(closes)

        if len(self.ema15_cache) < 35:
            return

        # ✅ USE ONLY CLOSED CANDLE
        signal_candle = candles[-2]
        prev_candle = candles[-3]
        signal_time = signal_candle["date"].astimezone(IST)

        # ✅ Prevent duplicate processing
        if self.last_processed_candle_time == signal_time:
            return
        self.last_processed_candle_time = signal_time

        # ✅ ENSURE candle is really closed
        if now < signal_time + timedelta(minutes=5):
            return

        ema15 = self.ema15_cache[-2]
        ema21 = self.ema21_cache[-2]
        nifty_spot = closes[-1]

        uptrend = ema15 > ema21 and abs(ema15 - ema21) > 3
        downtrend = ema15 < ema21 and abs(ema15 - ema21) > 3

        if now.time() >= ENTRY_END_TIME:
            return

        # ✅ Trade lock rules
        if self.current_trade_active:
            logger.info("Active trade running. Skipping new entry...")
            return

        if self.sl_count_today >= 2:
            logger.warning("Max 2 Stoploss reached. Trading stopped for today.")
            return

        bullish = self.is_bullish_rejection(signal_candle, ema15, ema21)
        bearish = self.is_bearish_rejection(signal_candle, ema15, ema21)

        logger.info(f"""
                    ✅ CLOSED Candle Evaluated @ {signal_time}
                    O:{signal_candle['open']} H:{signal_candle['high']}
                    L:{signal_candle['low']} C:{signal_candle['close']}
                    ema15:{ema15:.2f} ema21:{ema21:.2f}
                    emaDiff: {abs(ema15 - ema21)}
                    Trend: {'UP' if uptrend else 'DOWN' if downtrend else 'SIDEWAYS'}
                    BullishRej: {bullish}
                    BearishRej: {bearish}
                    """)

        if uptrend and bullish:
            logger.info("🚀 Bullish rejection + uptrend → CE Entry")
            self._enter_long_ce(nifty_spot)
            self.last_signal_candle_time = signal_time
            self.current_trade_active = True

        if downtrend and bearish:
            logger.info("🔻 Bearish rejection + downtrend → PE Entry")
            self._enter_short_pe(signal_candle, prev_candle, nifty_spot)
            self.last_signal_candle_time = signal_time
            self.current_trade_active = True

    # -------------------- Entry logic --------------------

    def _enter_long_ce(self, spot_price: float):
        """
        Long CE logic:
        - Choose 1 strike above ATM CE
        - Entry at option LTP at signal time
        - SL = previous candle low (on option price approx via %)
        - Target = Entry + 2 * (Entry - SL)
        """
        # ce_strike = get_ce_strike_for_long(spot_price)
        tsym = get_nifty_option_symbol(spot_price, "UP")

        if not tsym:
            return

        opt_token = get_instrument_token(tsym)
        opt_candles = self._fetch_recent_candles(opt_token)

        option_ltp = self.client.get_ltp(f"NFO:{tsym}")
        opt_trigger_candle = opt_candles[-2]
        opt_low = opt_trigger_candle["low"]
        opt_close = opt_trigger_candle["close"]

        # Approximate SL from previous candle low on underlying:
        # Using percentage move from spot instead of actual option candle.
        # This is a simplification: option SL = entry_price *

        stop_loss = opt_low

        # Risk-reward 1:2
        target = opt_close + 2 * (opt_close - opt_low)

        logger.info(
            "opt_low: ", opt_low
        )

        logger.info(
            "opt_low: ", opt_low
        )

        logger.info(
            "opt_low: ", opt_low
        )

        trade = self.order_manager.buy_option_trade(
            symbol=tsym,
            qty=self.quantity,
            entry_price=option_ltp,
            stop_loss=stop_loss,
            target=target,
        )

        if trade:
            self.current_trade_active = True

    def _enter_short_pe(self, spot_price: float):
        """
        Short (PE buy) logic:
        - Choose 1 strike below ATM PE
        - Entry at option LTP at signal time
        - SL = previous candle low (as per your original spec, though
          conventionally we'd often use previous HIGH for shorts – commented here)
        - Target = Entry + 2 * (Entry - SL)
        """
        #pe_strike = get_pe_strike_for_short(spot_price)
        tsym = get_nifty_option_symbol(spot_price, "DOWN")
        if not tsym:
            return
        opt_token = get_instrument_token(tsym)
        opt_candles = self._fetch_recent_candles(opt_token)

        opt_trigger_candle = opt_candles[-2]
        opt_low = opt_trigger_candle["low"]
        opt_close = opt_trigger_candle["close"]
        if not tsym:
            return

        option_ltp = self.client.get_ltp(f"NFO:{tsym}")

        # Using previous low of underlying as proxy for option SL (documented assumption)
        #stop_loss = option_ltp - option_ltp * pct
        stop_loss = opt_low

        # Risk-reward 1:2
        target = opt_close + 2 * (opt_close - opt_low)

        trade = self.order_manager.buy_option_trade(
            symbol=tsym,
            qty=self.quantity,
            entry_price=option_ltp,
            stop_loss=stop_loss,
            target=target,
        )

        if trade:
            self.current_trade_active = True

        # ================= REJECTION LOGIC =================

    def is_bullish_rejection(self, candle: Dict, ema15: float, ema21: float) -> bool:

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

    def is_bearish_rejection(self, candle: Dict, ema15: float, ema21: float) -> bool:

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

