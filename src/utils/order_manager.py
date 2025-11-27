# src/utils/order_manager.py
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from kiteconnect import KiteConnect
from src.utils.logger import logger
from src.zerodha_client import ZerodhaClient


@dataclass
class OpenTrade:
    symbol: str
    qty: int
    direction: str                  # LONG / SHORT
    entry_transaction_type: str     # BUY / SELL
    entry_price: float
    stop_loss: float
    target: float
    entry_time: datetime
    entry_order_id: str
    trade_type: str = "NORMAL"      # NORMAL / OPTION_BUY
    exit_order_id: Optional[str] = None
    status: str = "OPEN"            # OPEN / TARGET_HIT / SL_HIT / FORCE_EXIT


class OrderManager:
    """
    Central Trade Manager
    - Futures + Option Buy support
    - Safe exit logic
    - LTP monitoring
    """

    def __init__(self, client: ZerodhaClient, kite: KiteConnect):
        self.client = client
        self.kite = kite
        self.trades: List[OpenTrade] = []

    # =====================================================
    # GENERIC ENTRY
    # =====================================================

    def enter_trade(self, symbol, qty, direction, entry_price, stop_loss, target) -> OpenTrade:

        if direction == "LONG":
            transaction_type = self.kite.TRANSACTION_TYPE_BUY
        elif direction == "SHORT":
            transaction_type = self.kite.TRANSACTION_TYPE_SELL
        else:
            raise ValueError(f"Invalid trade direction: {direction}")

        order_id = self.client.place_market_order(
            symbol=symbol,
            qty=qty,
            transaction_type=transaction_type,
            product=self.kite.PRODUCT_MIS,
        )

        trade = OpenTrade(
            symbol=symbol,
            qty=qty,
            direction=direction,
            entry_transaction_type=transaction_type,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            entry_time=datetime.now(),
            entry_order_id=order_id,
            trade_type="NORMAL"
        )

        self.trades.append(trade)
        logger.success(
            f"Entered {direction} Trade {symbol} | "
            f"Entry={entry_price:.2f} SL={stop_loss:.2f} Target={target:.2f}"
        )
        return trade

    # =====================================================
    # OPTION BUY ENTRY
    # =====================================================

    def buy_option_trade(self, symbol, qty, entry_price, stop_loss, target) -> OpenTrade:

        logger.info(
            f"Option BUY {symbol} | Entry={entry_price:.2f} SL={stop_loss:.2f} Target={target:.2f}"
        )

        try:

            order_id = self.client.place_market_order(
                symbol=symbol,
                qty=qty,
                transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                product=self.kite.PRODUCT_MIS,
            )
        except Exception as e:
            logger.warning(f"⚠️ Order placement failed for {symbol}: {str(e)}")
            return None

        if not order_id:
            logger.warning(f"⚠️ Order NOT executed for {symbol}. Skipping trade registration.")
            return None

        trade = OpenTrade(
            symbol=symbol,
            qty=qty,
            direction="LONG",
            entry_transaction_type=self.kite.TRANSACTION_TYPE_BUY,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            entry_time=datetime.now(),
            entry_order_id=order_id,
            trade_type="OPTION_BUY"
        )

        self.trades.append(trade)
        logger.success(
            f"Option BUY {symbol} | Entry={entry_price:.2f} SL={stop_loss:.2f} Target={target:.2f}"
        )
        return trade

    # =====================================================
    # MONITOR ALL TRADES
    # =====================================================

    def monitor_trades(self):
        """
        Generic monitor for all trades (futures + options)
        """

        for trade in list(self.trades):

            if trade.status != "OPEN":
                continue

            ltp = self.client.get_ltp(f"NFO:{trade.symbol}")
            if ltp is None:
                continue

            if trade.entry_transaction_type == self.kite.TRANSACTION_TYPE_BUY:
                if ltp >= trade.target:
                    self._exit_trade(trade, "TARGET_HIT")
                elif ltp <= trade.stop_loss:
                    self._exit_trade(trade, "SL_HIT")
            else:
                if ltp <= trade.target:
                    self._exit_trade(trade, "TARGET_HIT")
                elif ltp >= trade.stop_loss:
                    self._exit_trade(trade, "SL_HIT")

    # =====================================================
    # MONITOR OPTION BUY TRADES ONLY
    # =====================================================

    def monitor_buy_option_trades(self):
        """
        Monitor only OPTION_BUY trades.
        Exit on SL or Target based on LTP.
        """

        for trade in list(self.trades):

            if trade.status != "OPEN":
                continue

            if trade.trade_type != "OPTION_BUY":
                continue

            ltp = self.client.get_ltp(f"NFO:{trade.symbol}")
            if ltp is None:
                continue

            if ltp >= trade.target:
                self._exit_trade(trade, "TARGET_HIT")

            elif ltp <= trade.stop_loss:
                self._exit_trade(trade, "SL_HIT")

    # =====================================================
    # SAFE EXIT HANDLER
    # =====================================================

    def _exit_trade(self, trade: OpenTrade, reason: str):

        exit_transaction_type = (
            self.kite.TRANSACTION_TYPE_SELL
            if trade.entry_transaction_type == self.kite.TRANSACTION_TYPE_BUY
            else self.kite.TRANSACTION_TYPE_BUY
        )

        order_id = self.client.place_market_order(
            symbol=trade.symbol,
            qty=trade.qty,
            transaction_type=exit_transaction_type,
            product=self.kite.PRODUCT_MIS,
        )

        if order_id:
            trade.exit_order_id = order_id
            trade.status = reason

            logger.success(
                f"Exit {reason} | {trade.symbol} qty={trade.qty}, order_id={order_id}"
            )

    # =====================================================
    # FORCE SQUARE OFF
    # =====================================================

    def force_square_off_all(self):

        logger.warning("Force square-off initiated...")

        for trade in self.trades:
            if trade.status == "OPEN":
                self._exit_trade(trade, "FORCE_EXIT")
