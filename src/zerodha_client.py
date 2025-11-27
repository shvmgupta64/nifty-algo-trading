# src/zerodha_client.py
from typing import List, Dict, Optional
from datetime import datetime
from .config import Config
from .utils.logger import logger

class ZerodhaClient:
    def __init__(self, kite):
        self.kite = kite

    # ---------- Basic APIs ----------
    def get_profile(self):
        return self.kite.profile()

    def get_ltp(self, symbol):
        data = self.kite.ltp(symbol)
        return list(data.values())[0]["last_price"]

    def get_positions(self):
        return self.kite.positions()

    # ---------- Historical candles ----------

    def get_historical_candles(
            self,
            instrument_token: int,
            from_dt: datetime,
            to_dt: datetime,
            interval: str = "5minute",
    ) -> List[Dict]:
        """
        Wraps kite.historical_data.
        Returns list of dicts with keys: date, open, high, low, close, volume
        """
        logger.debug(
            f"Fetching candles token={instrument_token}, "
            f"from={from_dt}, to={to_dt}, interval={interval}"
        )
        return self.kite.historical_data(
            instrument_token, from_dt, to_dt, interval, continuous=False, oi=False
        )

        # ---------- Instruments / options helpers ----------

    def _load_nfo_instruments(self) -> List[Dict]:

        if self._nfo_instruments_cache is None:
            logger.info("Loading NFO instruments (this may take a few seconds)...")
            self._nfo_instruments_cache = self.kite.instruments("NFO")
        return self._nfo_instruments_cache

    def get_nifty_option_symbol(
            self, strike: int, option_type: str
    ) -> Optional[str]:
        """
        Return nearest-expiry NIFTY option tradingsymbol for given strike and type.

        option_type: "CE" or "PE"
        """
        instruments = self._load_nfo_instruments()
        today = datetime.now().date()

        candidates = [
            inst
            for inst in instruments
            if inst.get("name") == "NIFTY"
               and inst.get("instrument_type") == option_type
               and int(inst.get("strike", 0)) == int(strike)
               and inst.get("expiry") >= today
        ]

        if not candidates:
            logger.error(f"No NIFTY {option_type} instrument found for strike {strike}")
            return None

        # Pick nearest expiry
        candidates.sort(key=lambda x: x["expiry"])
        tsym = candidates[0]["tradingsymbol"]
        logger.info(
            f"Selected {option_type} {strike} => tradingsymbol={tsym}, "
            f"expiry={candidates[0]['expiry']}"
        )
        return tsym

    # ---------- Order helpers ----------

    def place_market_order(
            self,
            symbol: str,
            qty: int,
            transaction_type: str,
            product: str = "MIS",
            variety: str = "regular",
            tag: str = "EMA_REJECTION_ALGO",
    ) -> str:
        """
        Place market order and return order_id.
        transaction_type: kite.TRANSACTION_TYPE_BUY / SELL
        """
        logger.info(
            f"Placing MARKET order: {transaction_type} {qty} of {symbol}, product={product}"
        )
        order_id = self.kite.place_order(
            variety=variety,
            exchange="NFO",
            tradingsymbol=symbol,
            transaction_type=transaction_type,
            quantity=qty,
            product=product,
            order_type=self.kite.ORDER_TYPE_MARKET,
            validity=self.kite.VALIDITY_DAY,
            tag=tag,
        )
        logger.success(f"Order placed. order_id={order_id}")
        return order_id

    def exit_position_market(self, symbol: str, qty: int) -> Optional[str]:
        """
        Simple market exit helper (sell for longs).
        """
        try:
            logger.info(f"Exiting position: SELL {qty} of {symbol}")
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=symbol,
                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                quantity=qty,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
                validity=self.kite.VALIDITY_DAY,
                tag="EMA_REJECTION_EXIT",
            )
            logger.success(f"Exit order placed. order_id={order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to exit position for {symbol}: {e}")
            return None
'''
class ZerodhaClient:
    """
    Thin wrapper around KiteConnect to:
    - Initialize connection using config
    - Provide helper methods (get_ltp, place_order, etc.)
    """
    
    def __init__(self) -> None:
        Config.validate()

        self.api_key = Config.KITE_API_KEY
        self.api_secret = Config.KITE_API_SECRET
        self.access_token = Config.KITE_ACCESS_TOKEN

        logger.info("Initializing KiteConnect client...")
        self.kite = KiteConnect(api_key=self.api_key)
        self.kite.set_access_token(self.access_token)

        logger.success("KiteConnect initialized with access token")

    # ---------- Utility methods ----------

    def get_profile(self) -> Dict[str, Any]:
        """Fetch Zerodha user profile (good test that API works)."""
        logger.info("Fetching user profile...")
        profile = self.kite.profile()
        logger.success(f"Got profile for user_id={profile.get('user_id')}")
        return profile

    def get_ltp(self, instrument: str) -> float:
        """
        Get last traded price (LTP) for a given instrument token or tradingsymbol.
        For indices, use 'NSE:NIFTY 50' etc.
        """
        logger.info(f"Fetching LTP for {instrument}...")
        data = self.kite.ltp(instrument)
        ltp = data[instrument]["last_price"]
        logger.info(f"LTP for {instrument} = {ltp}")
        return ltp

    def get_positions(self) -> Dict[str, Any]:
        logger.info("Fetching positions...")
        positions = self.kite.positions()
        logger.success("Positions fetched")
        return positions

    def get_orders(self) -> List[Dict[str, Any]]:
        logger.info("Fetching orders...")
        orders = self.kite.orders()
        logger.success(f"Got {len(orders)} orders")
        return orders

    # We'll add place_order, modify_order, cancel_order later
'''