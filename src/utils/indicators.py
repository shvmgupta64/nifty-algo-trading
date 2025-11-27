# src/utils/indicators.py
from typing import List
import math


def ema(values: List[float], period: int) -> List[float]:
    """
    Simple EMA implementation.
    Returns list of EMA values of same length as input.
    """
    if not values or period <= 0:
        return []

    k = 2 / (period + 1)
    emas = [values[0]]  # seed with first value

    for price in values[1:]:
        emas.append(price * k + emas[-1] * (1 - k))

    return emas


def ema_angle_is_up(ema_values: List[float], lookback: int = 5) -> bool:
    """
    Approximate 30-degree upward EMA slope.

    We treat 1 candle = 1 unit on x-axis and price difference on y-axis.
    angle = atan( (ema_now - ema_past) / lookback )

    If angle >= 30 degrees (pi/6 rad) -> considered "trending up strongly".
    """
    if len(ema_values) < lookback + 1:
        return False

    recent = ema_values[-1]
    past = ema_values[-lookback - 1]
    delta = recent - past
    angle_rad = math.atan(delta / lookback)
    return angle_rad >= math.pi / 6  # 30 degrees


def ema_angle_is_down(ema_values: List[float], lookback: int = 5) -> bool:
    """
    Same logic as ema_angle_is_up but for downtrend.
    """
    if len(ema_values) < lookback + 1:
        return False

    recent = ema_values[-1]
    past = ema_values[-lookback - 1]
    delta = recent - past
    angle_rad = math.atan(delta / lookback)
    return angle_rad <= -math.pi / 6  # -30 degrees
