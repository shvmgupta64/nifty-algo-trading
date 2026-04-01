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

def month_code(dt: datetime) -> str:
    m = dt.month
    if 1 <= m <= 9:
        return str(m)
    return {10: "O", 11: "N", 12: "D"}[m]

def get_expiry_code(today):

    #next_tue = get_next_tuesday(today)
    #last_tue = get_last_tuesday_of_month(today)
    '''
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
    '''
    next_exp = get_next_week_tuesday(today)  # your function

    # monthly expiry = last Tuesday of that month (no day in symbol)
    last_tue = get_last_tuesday_of_month(next_exp)

    yy = next_exp.strftime("%y")

    if next_exp.date() == last_tue.date():
        # Monthly: NIFTY26JAN...
        mon = next_exp.strftime("%b").upper()
        return f"{yy}{mon}"
    else:
        # Weekly: NIFTY26106...
        mcode = month_code(next_exp)
        dd = next_exp.strftime("%d")
        return f"{yy}{mcode}{dd}"

# =========================================================
# STRIKE SELECTION
# =========================================================

def get_strike_price(ltp, trend):
    if trend.upper() == "UP":
        return int(math.floor(ltp / 50) * 50)
    elif trend.upper() == "DOWN":
        return int(math.ceil(ltp / 50) * 50)
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
'''
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

'''
def get_instrument_token(trading_symbol, max_backtrack_days=7):
    """
    Returns: (resolved_symbol, instrument_token)

    Behavior:
    - Try the exact trading_symbol.
    - If not found in Kite instruments, shift weekly expiry date backward by 1 trading day
      (skipping weekends) and retry until found.
    """

    def is_weekend(dt_obj: datetime) -> bool:
        return dt_obj.weekday() >= 5  # Sat/Sun

    def prev_trading_day(dt_obj: datetime) -> datetime:
        dt_obj -= timedelta(days=1)
        while is_weekend(dt_obj):
            dt_obj -= timedelta(days=1)
        return dt_obj

    def month_from_code(mcode: str) -> int:
        if mcode.isdigit():  # "1".."9"
            return int(mcode)
        return {"O": 10, "N": 11, "D": 12}[mcode]  # Oct/Nov/Dec

    def is_weekly_expiry_code(expiry: str) -> bool:
        # Weekly: yy + mcode + dd => total 5 chars and last two are digits
        return len(expiry) == 5 and expiry[3:5].isdigit()

    def shift_symbol_to_prev_day(sym: str) -> str:
        """
        Shifts ONLY weekly expiry by -1 trading day.
        Example: NIFTY2630325650PE -> NIFTY2630225650PE
        """
        if not sym.startswith("NIFTY"):
            return sym

        prefix = "NIFTY"
        if len(sym) < 5 + 5 + 2:
            return sym

        expiry = sym[5:10]      # 5 chars (yy mcode dd)
        opt_type = sym[-2:]     # CE/PE
        strike = sym[10:-2]     # middle

        if not is_weekly_expiry_code(expiry):
            # Monthly codes like 26MAR: no day component to shift
            return sym

        yy = int(expiry[0:2])
        mcode = expiry[2]
        dd = int(expiry[3:5])

        year = 2000 + yy
        month = month_from_code(mcode)

        cur_dt = datetime(year, month, dd)
        prev_dt = prev_trading_day(cur_dt)

        new_expiry = f"{prev_dt.strftime('%y')}{month_code(prev_dt)}{prev_dt.strftime('%d')}"
        return f"{prefix}{new_expiry}{strike}{opt_type}"

    # ---- Fetch instruments list once
    url = "https://api.kite.trade/instruments"
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        raise Exception("Failed to fetch instruments list from Zerodha")

    csv_rows = list(csv.DictReader(StringIO(response.text)))

    # Fast lookup: NFO-OPT tradingsymbol -> token
    token_map = {}
    for row in csv_rows:
        if row.get("segment") == "NFO-OPT":
            ts = row.get("tradingsymbol")
            if ts:
                token_map[ts] = int(row["instrument_token"])

    # ---- Try original, then backtrack by shifting expiry day
    sym = trading_symbol
    tried = []

    for _ in range(max_backtrack_days + 1):
        tried.append(sym)

        token = token_map.get(sym)
        if token is not None:
            return sym, token

        next_sym = shift_symbol_to_prev_day(sym)

        # If no change (monthly/unknown), stop
        if next_sym == sym:
            break

        sym = next_sym

    raise Exception(
        f"Instrument token not found for symbol: {trading_symbol}\n"
        f"Tried:\n- " + "\n- ".join(tried)
    )

# =========================================================
# MAIN EXECUTION
# =========================================================

if __name__ == "__main__":
    ltp = float(input("Enter current NIFTY LTP: "))
    trend = input("Enter Trend (UP / DOWN): ")

    '''
    symbol = get_nifty_option_symbol(ltp, trend)
    token = get_instrument_token(symbol)

    print("✅ Trading Symbol :", symbol)
    print("✅ Instrument Token:", token)
    '''
    symbol = get_nifty_option_symbol(ltp, trend)
    resolved_symbol, token = get_instrument_token(symbol)

    print("✅ Trading Symbol :", resolved_symbol)
    print("✅ Instrument Token:", token)
