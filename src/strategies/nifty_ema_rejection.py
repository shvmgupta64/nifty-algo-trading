# src/strategies/nifty_ema_rejection_futures.py
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import pytz
from kiteconnect import KiteConnect
from src.zerodha_client import ZerodhaClient
from src.utils.indicators import ema, ema_angle_is_up, ema_angle_is_down
from src.utils.order_manager import OrderManager
from src.utils.logger import logger

IST = pytz.timezone("Asia/Kolkata")

NIFTY_UNDERLYING_TOKEN = 256265
NIFTY_FUT_SYMBOL = "NIFTY25NOVFUT"

ENTRY_END_TIME = datetime.strptime("15:00:00", "%H:%M:%S").time()
FORCE_EXIT_TIME = datetime.strptime("15:15:00", "%H:%M:%S").time()


class NiftyEMARejectionStrategy:

    def __init__(self, kite: KiteConnect, client: ZerodhaClient):
        self.kite = kite
        self.client = client
        self.order_manager = OrderManager(client, kite)

        self.last_signal_candle_time: Optional[datetime] = None
        self.last_processed_candle_time: Optional[datetime] = None

        self.quantity = 50

        self.cached_closes = []
        self.ema15_cache = []
        self.ema21_cache = []

        # 🔹 Resolve current month NIFTY futures symbol dynamically
        self.nifty_fut_symbol: str = self._get_current_month_nifty_fut_symbol()
        logger.info(f"Using NIFTY futures symbol: {self.nifty_fut_symbol}")

        # ================= UTILITIES =================

    def _get_current_month_nifty_fut_symbol(self) -> str:
        """
        Fetch NFO instruments and pick the nearest-expiry NIFTY FUT.
        This effectively gives you the current/front month NIFTY future.
        """
        today = datetime.now(IST).date()
        fallback = "NIFTY25NOVFUT"  # keep some fallback

        try:
            instruments = self.kite.instruments("NFO")
        except Exception as e:
            logger.error(f"Failed to fetch NFO instruments, using fallback FUT symbol. Error: {e}")
            return fallback

        nifty_futs = []
        for ins in instruments:

            try:
                if (
                        ins.get("segment") == "NFO-FUT"
                        and ins.get("name") == "NIFTY"
                        and ins.get("instrument_type") == "FUT"
                        #and ins.get("expiry") is not None
                        #and ins["expiry"].date() >= today
                ):
                    nifty_futs.append(ins)
            except Exception:
                continue

        if not nifty_futs:
            logger.error("No NIFTY futures instruments found; falling back to hardcoded symbol.")
            return fallback

        front = sorted(nifty_futs, key=lambda x: x["expiry"])[0]
        symbol = front["tradingsymbol"]
        return symbol

    def _get_fut_ltp(self) -> Optional[float]:
        """
        Get live LTP for the current month NIFTY future.
        """
        try:
            data = self.kite.ltp([f"NFO:{self.nifty_fut_symbol}"])
            key = next(iter(data))
            return data[key]["last_price"]
        except Exception as e:
            logger.error(f"Failed to fetch FUT LTP for {self.nifty_fut_symbol}: {e}")
            return None

    # ================= MAIN LOOP =================

    def run(self):
        logger.info("Starting NIFTY FUTURES EMA Rejection Strategy...")

        while True:
            now = datetime.now(IST)

            if now.time() >= FORCE_EXIT_TIME:
                self.order_manager.force_square_off_all()
                logger.info("Force exit done. Strategy stopped.")
                break

            candles = self._fetch_recent_candles()
            if candles:
                self._process_candles(candles, now)

            self.order_manager.monitor_trades()
            import time
            time.sleep(5)

    # ================= DATA FETCH =================

    def _fetch_recent_candles(self):
        now = datetime.now(IST)
        from_dt = (now - timedelta(days=1)).replace(hour=9, minute=15, second=0)

        return self.client.get_historical_candles(
            instrument_token=NIFTY_UNDERLYING_TOKEN,
            from_dt=from_dt,
            to_dt=now,
            interval="5minute",
        )

    # ================= EMA CACHE =================

    def _update_ema_cache(self, closes: List[float]):
        if not self.cached_closes:
            self.cached_closes = closes
            self.ema15_cache = ema(closes, 15)
            self.ema21_cache = ema(closes, 21)
            return

        new_closes = closes[len(self.cached_closes):]
        for price in new_closes:
            self.ema15_cache.append((price * 2 / 16) + self.ema15_cache[-1] * (1 - 2 / 16))
            self.ema21_cache.append((price * 2 / 22) + self.ema21_cache[-1] * (1 - 2 / 22))
        self.cached_closes = closes

    # ================= CORE LOGIC =================

    def _process_candles(self, candles: List[Dict], now: datetime):

        closes = [c["close"] for c in candles]
        self._update_ema_cache(closes)

        if len(candles) < 40:
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

        uptrend = ema15 > ema21 and ema_angle_is_up(self.ema15_cache[:-1])
        downtrend = ema15 < ema21 and ema_angle_is_down(self.ema15_cache[:-1])

        if now.time() >= ENTRY_END_TIME:
            return

        if self.last_signal_candle_time and signal_time <= self.last_signal_candle_time:
            return

        bullish = self.is_bullish_rejection(signal_candle, ema15, ema21)
        bearish = self.is_bearish_rejection(signal_candle, ema15, ema21)

        logger.info(f"""
            ✅ CLOSED Candle Evaluated @ {signal_time}
            O:{signal_candle['open']} H:{signal_candle['high']}
            L:{signal_candle['low']} C:{signal_candle['close']}
            ema15:{ema15:.2f} ema21:{ema21:.2f}
            Trend: {'UP' if uptrend else 'DOWN' if downtrend else 'SIDEWAYS'}
            BullishRej: {bullish}
            BearishRej: {bearish}
            """)


        if uptrend and bullish:
            self._enter_long_fut(signal_candle, prev_candle)
            self.last_signal_candle_time = signal_time

        if downtrend and bearish:
            self._enter_short_fut(signal_candle, prev_candle)
            self.last_signal_candle_time = signal_time

        # ================= SL / TARGET HELPERS =================

    def _calculate_sl_long(self, signal_candle: Dict, prev_candle: Dict) -> float:
        """
        SL for LONG in NIFTY points – below the rejection zone.
        """
        return min(signal_candle["low"], prev_candle["low"])

    def _calculate_sl_short(self, signal_candle: Dict, prev_candle: Dict) -> float:
        """
        SL for SHORT in NIFTY points – above the rejection zone.
        """
        return max(signal_candle["high"], prev_candle["high"])

    # ================= TRADE EXECUTION =================
    def _enter_long_fut(self, signal_candle: Dict, prev_candle: Dict):

        fut_entry = self._get_fut_ltp()
        if fut_entry is None:
            logger.error("Skipping LONG entry: could not fetch FUT LTP")
            return

        # --- NIFTY (index) based levels ---
        underlying_entry = signal_candle["close"]
        sl_underlying = self._calculate_sl_long(signal_candle, prev_candle)
        risk_points = underlying_entry - sl_underlying

        if risk_points <= 0:
            logger.info(f"Invalid LONG risk_points={risk_points}, skipping trade.")
            return

        target_points = 2 * risk_points  # RR 1:2

        # --- Apply those point distances on FUT price ---
        sl_fut = fut_entry - risk_points
        target_fut = fut_entry + target_points

        logger.info(
            f"LONG FUT ENTRY: fut_entry={fut_entry:.2f}, "
            f"risk_points={risk_points:.2f}, sl_fut={sl_fut:.2f}, target_fut={target_fut:.2f}"
        )

        self.order_manager.enter_trade(
            symbol=self.nifty_fut_symbol,
            qty=self.quantity,
            direction="LONG",
            entry_price=fut_entry,
            stop_loss=sl_fut,
            target=target_fut
        )

    def _enter_short_fut(self, signal_candle: Dict, prev_candle: Dict):
        fut_entry = self._get_fut_ltp()
        if fut_entry is None:
            logger.error("Skipping SHORT entry: could not fetch FUT LTP")
            return

        # --- NIFTY (index) based levels ---
        underlying_entry = signal_candle["close"]
        sl_underlying = self._calculate_sl_short(signal_candle, prev_candle)
        risk_points = sl_underlying - underlying_entry  # positive for short

        if risk_points <= 0:
            logger.info(f"Invalid SHORT risk_points={risk_points}, skipping trade.")
            return

        target_points = 2 * risk_points  # RR 1:2

        # --- Apply those point distances on FUT price ---
        sl_fut = fut_entry + risk_points
        target_fut = fut_entry - target_points

        logger.info(
            f"SHORT FUT ENTRY: fut_entry={fut_entry:.2f}, "
            f"risk_points={risk_points:.2f}, sl_fut={sl_fut:.2f}, target_fut={target_fut:.2f}"
        )

        self.order_manager.enter_trade(
            symbol=self.nifty_fut_symbol,
            qty=self.quantity,
            direction="SHORT",
            entry_price=fut_entry,
            stop_loss=sl_fut,
            target=target_fut,
        )

        # ================= REJECTION LOGIC =================

    def is_bullish_rejection(self, candle: Dict, ema15: float, ema21: float) -> bool:
        body = candle["close"] - candle["open"]
        return (
                body >= 10
                and candle["close"] > candle["open"]
                and min(abs(candle["low"] - ema15), abs(candle["low"] - ema21)) <= 5
        )

    def is_bearish_rejection(self, candle: Dict, ema15: float, ema21: float) -> bool:
        body = candle["open"] - candle["close"]
        return (
                body >= 10
                and candle["open"] > candle["close"]
                and min(abs(candle["high"] - ema15), abs(candle["high"] - ema21)) <= 5
        )
