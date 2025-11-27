from kiteconnect import KiteConnect
import json

# Your API credentials
API_KEY = "lghm61s79jrhrswu"
ACCESS_TOKEN = "XfCaE22DI2n5I0tlV0vwCz21MtjqMieq"


def get_all_instruments(kite):
    """
    Fetch all instruments from Kite

    Args:
        kite: KiteConnect instance

    Returns:
        list: All available instruments
    """
    try:
        instruments = kite.instruments()
        print(f"Loaded {len(instruments)} total instruments")
        return instruments
    except Exception as e:
        print(f"Error fetching instruments: {e}")
        return None


def search_by_symbol(instruments, symbol):
    """
    Search instruments by trading symbol

    Args:
        instruments (list): List of all instruments
        symbol (str): Trading symbol to search (e.g., 'NIFTY', 'INFY')

    Returns:
        list: Matching instruments
    """

    print(f"\nSearching for symbol: {symbol}...")
    results = [inst for inst in instruments if symbol.upper() in inst.get('tradingsymbol', '').upper()]

    if results:
        print(f"Found {len(results)} instruments")
        return results
    else:
        print("No results found")
        return None


def search_by_name(instruments, name):
    """
    Search instruments by name

    Args:
        instruments (list): List of all instruments
        name (str): Name to search

    Returns:
        list: Matching instruments
    """

    print(f"\nSearching for name: {name}...")
    results = [inst for inst in instruments if name.upper() in inst.get('name', '').upper()]

    if results:
        print(f"Found {len(results)} instruments")
        return results
    else:
        print("No results found")
        return None


def search_nifty_options(instruments, option_type=None, expiry=None):
    """
    Search for NIFTY options (monthly and weekly)

    Args:
        instruments (list): List of all instruments
        option_type (str): 'CE' for Call, 'PE' for Put, None for both
        expiry (str): Filter by expiry date (e.g., '2025-12-04'), None for all

    Returns:
        list: NIFTY options matching criteria
    """

    print(f"\nSearching for NIFTY options...")
    results = [inst for inst in instruments if 'NIFTY' in inst.get('tradingsymbol', '')
               and inst.get('segment') in ['NFO-OPT', 'NFO']]

    if option_type:
        results = [inst for inst in results if option_type in inst.get('tradingsymbol', '')]

    if expiry:
        results = [inst for inst in results if inst.get('expiry') == expiry]

    if results:
        print(f"Found {len(results)} NIFTY options")
        return results
    else:
        print("No results found")
        return None


def search_banknifty_options(instruments, option_type=None, expiry=None):
    """
    Search for BANKNIFTY options (monthly and weekly)

    Args:
        instruments (list): List of all instruments
        option_type (str): 'CE' for Call, 'PE' for Put, None for both
        expiry (str): Filter by expiry date, None for all

    Returns:
        list: BANKNIFTY options matching criteria
    """

    print(f"\nSearching for BANKNIFTY options...")
    results = [inst for inst in instruments if 'BANKNIFTY' in inst.get('tradingsymbol', '')
               and inst.get('segment') in ['NFO-OPT', 'NFO']]

    if option_type:
        results = [inst for inst in results if option_type in inst.get('tradingsymbol', '')]

    if expiry:
        results = [inst for inst in results if inst.get('expiry') == expiry]

    if results:
        print(f"Found {len(results)} BANKNIFTY options")
        return results
    else:
        print("No results found")
        return None


def print_results(results, show_fields=None, limit=30):
    """
    Pretty print search results

    Args:
        results (list): List of instrument results
        show_fields (list): Specific fields to display (None = all important fields)
        limit (int): Maximum number to display
    """

    if not results:
        print("No results to display")
        return

    if not show_fields:
        show_fields = ['tradingsymbol', 'name', 'exchange', 'segment', 'instrument_token', 'expiry', 'strike']

    print(f"\nDisplaying first {min(limit, len(results))} results:\n")

    for idx, instrument in enumerate(results[:limit], 1):
        print(f"{idx}. ", end="")
        for i, field in enumerate(show_fields):
            value = instrument.get(field, 'N/A')
            if i < len(show_fields) - 1:
                print(f"{value} | ", end="")
            else:
                print(f"{value}")


# Example usage
if __name__ == "__main__":

    if API_KEY == "your_api_key_here" or ACCESS_TOKEN == "your_access_token_here":
        print("⚠️  SETUP REQUIRED!")
        print("\nSteps to get your credentials:")
        print("1. Go to https://kite.trade/ and log in to your account")
        print("2. Go to Settings > API Tokens")
        print("3. Create a new API key and note your API_KEY")
        print("4. Use the login URL to authenticate and get ACCESS_TOKEN")
        print("\nThen update the script with your credentials.\n")

    else:
        try:
            # Initialize Kiteconnect
            kite = KiteConnect(api_key=API_KEY)
            kite.set_access_token(ACCESS_TOKEN)

            print("✓ Successfully authenticated!\n")

            # Load all instruments (this takes a moment)
            all_instruments = get_all_instruments(kite)

            if all_instruments:
                # Example 1: Search for all NIFTY options
                nifty_options = search_nifty_options(all_instruments)
                if nifty_options:
                    print_results(nifty_options, limit=50)

                # Example 2: Search for NIFTY Call options only
                # nifty_calls = search_nifty_options(all_instruments, option_type='CE')
                # if nifty_calls:
                #     print_results(nifty_calls, limit=50)

                # Example 3: Search for BANKNIFTY options
                # banknifty_options = search_banknifty_options(all_instruments)
                # if banknifty_options:
                #     print_results(banknifty_options, limit=50)

                # Example 4: Search for a specific stock
                # infy = search_by_symbol(all_instruments, 'INFY')
                # if infy:
                #     print_results(infy)

        except Exception as e:
            print(f"Error: {e}")
            print("Please check your API_KEY and ACCESS_TOKEN")