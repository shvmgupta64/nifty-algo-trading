from kiteconnect import KiteConnect
from datetime import datetime

# Your API credentials
API_KEY = "lghm61s79jrhrswu"
ACCESS_TOKEN = "XfCaE22DI2n5I0tlV0vwCz21MtjqMieq"

# ============================================================================
# CONFIGURATION VARIABLES - MODIFY THESE
# ============================================================================
INSTRUMENT = "NIFTY"  # e.g., "NIFTY", "BANKNIFTY", "FINNIFTY"
STRIKE = 25000  # Strike price (e.g., 25000, 24900, 24800)
DIRECTION = "CE"  # "CE" for Call, "PE" for Put
EXPIRY = "2025-11-06"  # Expiry date in format "YYYY-MM-DD"


# ============================================================================


def get_all_instruments(kite):
    """Fetch all instruments from Kite"""
    try:
        instruments = kite.instruments()
        print(f"✓ Loaded {len(instruments)} total instruments\n")
        return instruments
    except Exception as e:
        print(f"Error fetching instruments: {e}")
        return None


def find_option_contract(instruments, instrument, strike, direction, expiry):
    """
    Find the exact option contract based on parameters

    Args:
        instruments (list): All instruments
        instrument (str): Base instrument (e.g., 'NIFTY')
        strike (int): Strike price
        direction (str): 'CE' or 'PE'
        expiry (str): Expiry date in format "YYYY-MM-DD"

    Returns:
        dict: Option contract details or None
    """

    print(f"Searching for option contract:")
    print(f"  Instrument: {instrument}")
    print(f"  Strike: {strike}")
    print(f"  Direction: {direction}")
    print(f"  Expiry: {expiry}\n")

    # Filter for matching options
    matching_options = [
        inst for inst in instruments
        if inst.get('tradingsymbol', '').startswith(instrument)
           and inst.get('segment') == 'NFO-OPT'
           and inst.get('strike') == strike
           and direction in inst.get('tradingsymbol', '')
           and str(inst.get('expiry')) == expiry
    ]

    if matching_options:
        option = matching_options[0]
        print(f"✓ Found option contract:")
        print(f"  Trading Symbol: {option.get('tradingsymbol')}")
        print(f"  Instrument Token: {option.get('instrument_token')}")
        print(f"  Strike: {option.get('strike')}")
        print(f"  Expiry: {option.get('expiry')}\n")
        return option
    else:
        print(f"✗ Option contract not found!\n")
        return None


def get_option_price(kite, option_contract):
    """
    Fetch current price of the option contract

    Args:
        kite: KiteConnect instance
        option_contract (dict): Option contract details

    Returns:
        dict: Price data or None
    """

    try:
        trading_symbol = option_contract.get('tradingsymbol')
        exchange = option_contract.get('exchange', 'NFO')

        # Format: exchange:tradingsymbol (e.g., 'NFO:NIFTY25NOV24000CE')
        instrument_identifier = f"{exchange}:{trading_symbol}"

        print(f"Fetching price for: {instrument_identifier}\n")

        # Get quote data
        quotes = kite.get_quote([instrument_identifier])

        if instrument_identifier in quotes:
            quote_data = quotes[instrument_identifier]

            print(f"{'=' * 60}")
            print(f"OPTION PRICE DATA")
            print(f"{'=' * 60}")
            print(f"Trading Symbol: {trading_symbol}")
            print(f"Last Traded Price (LTP): ₹{quote_data.get('last_price', 'N/A')}")
            print(f"Bid Price: ₹{quote_data.get('bid', 'N/A')}")
            print(f"Ask Price: ₹{quote_data.get('ask', 'N/A')}")
            print(f"Open: ₹{quote_data.get('ohlc', {}).get('open', 'N/A')}")
            print(f"High: ₹{quote_data.get('ohlc', {}).get('high', 'N/A')}")
            print(f"Low: ₹{quote_data.get('ohlc', {}).get('low', 'N/A')}")
            print(f"Close: ₹{quote_data.get('ohlc', {}).get('close', 'N/A')}")
            print(f"Volume: {quote_data.get('volume', 'N/A')}")
            print(f"Open Interest: {quote_data.get('oi', 'N/A')}")
            print(f"{'=' * 60}\n")

            return quote_data
        else:
            print(f"✗ Could not fetch quote for {instrument_identifier}\n")
            return None

    except Exception as e:
        print(f"Error fetching price: {e}\n")
        return None


def list_available_strikes(instruments, instrument, direction, expiry):
    """
    List all available strikes for a given instrument, direction and expiry

    Args:
        instruments (list): All instruments
        instrument (str): Base instrument (e.g., 'NIFTY')
        direction (str): 'CE' or 'PE'
        expiry (str): Expiry date
    """

    available = [
        inst for inst in instruments
        if inst.get('tradingsymbol', '').startswith(instrument)
           and inst.get('segment') == 'NFO-OPT'
           and direction in inst.get('tradingsymbol', '')
           and str(inst.get('expiry')) == expiry
    ]

    strikes = sorted(set(inst.get('strike') for inst in available if inst.get('strike')))

    print(f"\nAvailable strikes for {instrument} {direction} expiry {expiry}:")
    print(f"Total strikes: {len(strikes)}")
    print(f"Strikes: {strikes[:20]}...")  # Show first 20
    print()


# Main execution
if __name__ == "__main__":

    try:
        # Initialize Kiteconnect
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(ACCESS_TOKEN)

        print("✓ Successfully authenticated!\n")

        # Load all instruments
        all_instruments = get_all_instruments(kite)

        if all_instruments:
            print(f"{'=' * 60}")
            print(f"FETCHING OPTION PRICE")
            print(f"{'=' * 60}\n")

            # Find the option contract
            option_contract = find_option_contract(
                all_instruments,
                instrument=INSTRUMENT,
                strike=STRIKE,
                direction=DIRECTION,
                expiry=EXPIRY
            )

            if option_contract:
                # Fetch and display the price
                price_data = get_option_price(kite, option_contract)

                if not price_data:
                    print("Tip: Make sure the market is open or the contract is traded\n")
            else:
                # Show available options to help user
                print("Available options to choose from:\n")
                list_available_strikes(all_instruments, INSTRUMENT, "CE", EXPIRY)
                list_available_strikes(all_instruments, INSTRUMENT, "PE", EXPIRY)

    except Exception as e:
        print(f"Error: {e}")
        print("Please check your API_KEY and ACCESS_TOKEN")