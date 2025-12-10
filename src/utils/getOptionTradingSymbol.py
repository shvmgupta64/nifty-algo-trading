from datetime import datetime, timedelta
import calendar
import math
import requests
import csv
from io import StringIO

# =========================================================
# EXPIRY CALCULATION
# =========================================================

def get_next_tuesday(date):
    TUESDAY = 1
    days_ahead = TUESDAY - date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return date + timedelta(days=days_ahead)

def get_current_week_tuesday(date):
    TUESDAY = 1
    days_back = date.weekday() - TUESDAY
    if days_back >= 0:
        return date - timedelta(days=days_back)
    else:
        return date - timedelta(days=days_back + 7)

def get_next_week_tuesday(date):
    TUESDAY = 1

    # Find upcoming Tuesday of current week (or today if Tue)
    days_to_tue = (TUESDAY - date.weekday()) % 7
    current_week_tue = date + timedelta(days=days_to_tue)

    # If today is Mon or Tue of expiry week → skip this expiry
    if date.weekday() in (0, 1):
        return current_week_tue + timedelta(days=7)

    # Otherwise trade next upcoming expiry
    return current_week_tue

def get_last_tuesday_of_month(date):
    year = date.year
    month = date.month
    last_day = calendar.monthrange(year, month)[1]
    last_date = datetime(year, month, last_day)

    while last_date.weekday() != 1:
        last_date -= timedelta(days=1)

    return last_date


def get_expiry_code(today):

    #next_tue = get_next_tuesday(today)
    #last_tue = get_last_tuesday_of_month(today)
    next_tue = get_next_week_tuesday(today)
    last_tue = get_last_tuesday_of_month(next_tue)
    year = next_tue.strftime("%y")
    month = next_tue.strftime("%b").upper()
    day = next_tue.strftime("%d")

    # ✅ last weekly → monthly
    if next_tue.date() == last_tue.date():
        return f"{year}{month}"     # 25DEC
    else:
        return f"{year}D{day}"      # 25D02


# =========================================================
# STRIKE SELECTION
# =========================================================

def get_strike_price(ltp, trend):
    if trend.upper() == "UP":
        return int(math.ceil(ltp / 50) * 50)
    elif trend.upper() == "DOWN":
        return int(math.floor(ltp / 50) * 50)
    else:
        raise ValueError("Trend must be UP or DOWN")


# =========================================================
# TRADING SYMBOL GENERATION
# =========================================================

def get_nifty_option_symbol(ltp, trend):
    today = datetime.now()
    expiry = get_expiry_code(today)
    strike = get_strike_price(ltp, trend)
    option_type = "CE" if trend.upper() == "UP" else "PE"

    return f"NIFTY{expiry}{strike}{option_type}"


# =========================================================
# INSTRUMENT TOKEN FETCH (ZERODHA)
# =========================================================

def get_instrument_token(trading_symbol):
    """
    Fetch instrument token for given trading symbol using Zerodha instrument dump
    This avoids manual token handling and is 100% accurate.
    """

    url = "https://api.kite.trade/instruments"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception("Failed to fetch instruments list from Zerodha")

    csv_data = csv.DictReader(StringIO(response.text))

    for row in csv_data:
        if row["tradingsymbol"] == trading_symbol and row["segment"] == "NFO-OPT":
            return int(row["instrument_token"])

    raise Exception(f"Instrument token not found for symbol: {trading_symbol}")


# =========================================================
# MAIN EXECUTION
# =========================================================

if __name__ == "__main__":
    ltp = float(input("Enter current NIFTY LTP: "))
    trend = input("Enter Trend (UP / DOWN): ")

    symbol = get_nifty_option_symbol(ltp, trend)
    token = get_instrument_token(symbol)

    print("✅ Trading Symbol :", symbol)
    print("✅ Instrument Token:", token)
