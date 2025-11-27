# src/utils/candle_utils.py
from typing import Dict, List
import math


def is_bullish_rejection_candle(
    candle: Dict,
    ema20: float,
    ema30: float,
    min_body_pts: float = 10.0,
    ema_touch_tolerance: float = 5.0,
) -> bool:
    """
    Bullish rejection candle:
    - close > open
    - body size >= min_body_pts (close - open)
    - low/close comes "near" either EMA20 or EMA30 (within ema_touch_tolerance points)
    """
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    body = c - o

    if body < min_body_pts:
        return False
    if c <= o:
        return False

    # Distance of low and close from EMAs
    d1 = min(abs(l - ema20), abs(l - ema30))
    d2 = min(abs(c - ema20), abs(c - ema30))

    return min(d1, d2) <= ema_touch_tolerance


def is_bearish_rejection_candle(
    candle: Dict,
    ema20: float,
    ema30: float,
    min_body_pts: float = 10.0,
    ema_touch_tolerance: float = 5.0,
) -> bool:
    """
    Bearish rejection candle:
    - close < open
    - body size >= min_body_pts (open - close)
    - high/close comes "near" either EMA20 or EMA30
    """
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    body = o - c

    if body < min_body_pts:
        return False
    if c >= o:
        return False

    d1 = min(abs(h - ema20), abs(h - ema30))
    d2 = min(abs(c - ema20), abs(c - ema30))

    return min(d1, d2) <= ema_touch_tolerance


def get_atm_strike(spot_price: float, step: int = 50) -> int:
    """
    Get ATM strike rounded to nearest 'step' (NIFTY = 50).
    """
    return int(round(spot_price / step) * step)


def get_ce_strike_for_long(spot_price: float, step: int = 50) -> int:
    """
    For bullish setup: 1 strike ABOVE ATM for CE.
    """
    atm = get_atm_strike(spot_price, step)
    return atm + step


def get_pe_strike_for_short(spot_price: float, step: int = 50) -> int:
    """
    For bearish setup: 1 strike BELOW ATM for PE.
    """
    atm = get_atm_strike(spot_price, step)
    return atm - step
