"""
I will use this file to start my algo trading journey from the begining.
=======================================================================
mention your api key and secret key to get authorized.
=======================================================================
"""

import os
import sys
import webbrowser
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("ERROR: kiteconnect not installed. Run: pip install kiteconnect")
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================
# Load .env from project root
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

API_KEY: str = os.getenv("KITE_API_KEY", "")
API_SECRET: str = os.getenv("KITE_API_SECRET", "")
REDIRECT_URL = os.getenv("ZERODHA_REDIRECT_URL", "http://localhost:3000")
ENV_FILE_PATH = Path(r"C:\Users\Lenovo\Desktop\Algo\.env")


# ============================================================================
# OAUTH CALLBACK HANDLER
# ============================================================================
class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """
    Simple HTTP server to capture the OAuth callback.
    Zerodha redirects to this URL after user authorizes the app.
    """

    request_token = None

    def do_GET(self):
        """Handle the redirect from Zerodha."""
        # Parse the request token from query parameters
        query_params = parse_qs(urlparse(self.path).query)

        if 'request_token' in query_params:
            OAuthCallbackHandler.request_token = query_params['request_token'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
                        <html>
                        <head><title>Authorization Successful</title></head>
                        <body style="font-family: Arial; text-align: center; padding: 50px;">
                            <h1>Authorization Successful!</h1>
                            <p>Your Zerodha account has been authorized.</p>
                            <p>You can close this window and return to your terminal.</p>
                            <script>window.close();</script>
                        </body>
                        </html>
                        """
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Error: No request token received</h1></body></html>")

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def get_oauth_request_token(api_key: str, redirect_url: str) -> str:
    """
    Step 1: Generate OAuth login URL and open browser for user authorization.

    Returns:
        Request token after user authorizes
    """
    kite = KiteConnect(api_key=api_key)

    # Generate login URL
    login_url = kite.login_url()
    print("\n" + "=" * 70)
    print("🔐 ZERODHA OAUTH AUTHORIZATION")
    print("=" * 70)
    print(f"Opening browser to: {login_url}")
    print("\nPlease:")
    print("1. Login with your Zerodha credentials")
    print("2. Enter OTP")
    print("3. Approve the application access")
    print("4. Wait for redirect...")
    print("=" * 70 + "\n")

    # Open browser
    webbrowser.open(login_url)

    # Start local HTTP server to capture callback
    print("Starting local server on http://localhost:8080 to capture callback...")
    server = HTTPServer(('localhost', 3000), OAuthCallbackHandler)

    # Set timeout to 5 minutes
    server.timeout = 300

    # Wait for callback
    while OAuthCallbackHandler.request_token is None:
        server.handle_request()

    server.server_close()
    request_token = OAuthCallbackHandler.request_token
    print(f"✓ Request token received: {request_token}\n")

    return request_token


def generate_access_token(api_key: str, api_secret: str, request_token: str) -> str:
    """
    Step 2: Exchange request token for access token.

    Args:
        api_key: Zerodha API Key
        api_secret: Zerodha API Secret
        request_token: Request token from OAuth callback

    Returns:
        Access token for API calls
    """
    kite = KiteConnect(api_key=api_key)

    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data['access_token']
        print(f"✓ Access token generated successfully")
        return access_token
    except Exception as e:
        print(f"ERROR: Failed to generate access token: {e}")
        sys.exit(1)

def load_token_from_env() -> str | None:
    if ENV_FILE_PATH.exists():
        with open(ENV_FILE_PATH) as f:
            for line in f:
                if line.startswith("KITE_ACCESS_TOKEN="):
                    return line.strip().split("=", 1)[1]
    return None
def save_token_to_env(token: str):
    """
    Save KITE_ACCESS_TOKEN into .env file at:
    c:\\Users\\Lenovo\\Desktop\\Algo\\.env
    """

    ENV_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing_lines = []
    if ENV_FILE_PATH.exists():
        with open(ENV_FILE_PATH, "r") as f:
            existing_lines = f.readlines()

    token_written = False
    new_lines = []

    for line in existing_lines:
        if line.startswith("KITE_ACCESS_TOKEN="):
            new_lines.append(f"KITE_ACCESS_TOKEN={token}\n")
            token_written = True
        else:
            new_lines.append(line)

    if not token_written:
        new_lines.append(f"\nKITE_ACCESS_TOKEN={token}\n")

    with open(ENV_FILE_PATH, "w") as f:
        f.writelines(new_lines)

    print(f"✅ Access token stored in .env file at: {ENV_FILE_PATH}")

def get_access_token(api_key: str, api_secret: str) -> str:
    """
    Get access token with automatic OAuth flow.
    Uses cached token if available, otherwise generates new one.
    """
    # Try to load cached token
    cached_token = load_token_from_env()
    if cached_token:
        print("🔎 Found cached access token. Validating...")

        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(cached_token)

        try:
            kite.profile()  # lightweight call to test token
            print("✅ Cached token is valid.")
            return cached_token
        except Exception as e:
            print("⚠ Cached token is INVALID or expired. Regenerating...")
            print(f"Reason: {e}")

    # Generate new token via OAuth
    print("Generating new access token via OAuth...")
    request_token = get_oauth_request_token(api_key, REDIRECT_URL)
    access_token = generate_access_token(api_key, api_secret, request_token)

    # Save for future use
    save_token_to_env(access_token)

    return access_token


def init_kite(api_key: str, api_secret: str) -> KiteConnect:
    """Initialize Kite Connect with automatic authentication."""
    access_token = get_access_token(api_key, api_secret)

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Final validation (double safety)
    try:
        kite.profile()
        print("✅ Kite session validated successfully.")
    except Exception:
        print("⚠ Token failed during validation. Re-authenticating...")

        request_token = get_oauth_request_token(api_key, REDIRECT_URL)
        new_token = generate_access_token(api_key, api_secret, request_token)

        save_token_to_env(new_token)
        kite.set_access_token(new_token)

    return kite


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main execution."""

    print("\n" + "=" * 70)
    print("🚀 ZERODHA AUTO-AUTHENTICATED PORTFOLIO ANALYZER")
    print("=" * 70)

    # Validate credentials

    if API_KEY == "your_api_key_here" or API_SECRET == "your_api_secret_here":
        print("\n❌ ERROR: API credentials not configured!")
        print("\nSetup instructions:")
        print("1. Set environment variables:")
        print("   export ZERODHA_API_KEY='your_key'")
        print("   export ZERODHA_API_SECRET='your_secret'")
        print("\n2. Or edit this script and update CONFIG section\n")
        sys.exit(1)

    # Initialize Kite with automatic authentication
    try:
        kite = init_kite(API_KEY, API_SECRET)
        print("\n✓ Connected to Zerodha Kite")
    except Exception as e:
        print(f"\n❌ Failed to initialize Kite: {e}")
        sys.exit(1)



if __name__ == "__main__":
    main()