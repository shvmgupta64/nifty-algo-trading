import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()

def auto_login():
    kite = KiteConnect(api_key=os.getenv("API_KEY"))

    if os.path.exists("access_token.txt"):
        with open("access_token.txt", "r") as f:
            token = f.read().strip()
            kite.set_access_token(token)
            return kite

    print("Go to this URL and login:")
    print(kite.login_url())

    request_token = input("Paste request_token here: ")

    data = kite.generate_session(
        request_token=request_token,
        api_secret=os.getenv("API_SECRET")
    )

    access_token = data["access_token"]

    with open("access_token.txt", "w") as f:
        f.write(access_token)

    kite.set_access_token(access_token)
    print("Access token saved.")

    return kite


# =========================================================
# MAIN EXECUTION
# =========================================================

if __name__ == "__main__":

    symbol = auto_login()
    #token = get_instrument_token(symbol)

    print("✅ Trading Symbol :", symbol)
    #print("✅ Instrument Token:", token)
