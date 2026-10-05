#!/usr/bin/env python3
"""
HDFC Sky Authentication & Token Generator
Generates and refreshes authorization tokens using Phone Number, OTP, and Password/PIN
according to the official HDFC Sky OpenAPI authentication flow.
"""

import os
import sys
import getpass
import requests

# ==========================================
# BUILT-IN .ENV LOADER
# ==========================================
def _load_env_file():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_env_file()

# Base URL for HDFC Sky OpenAPI
BASE_URL = os.getenv("HDFCSKY_BASE_URL", "https://developer.hdfcsky.com")
UAT_BASE_URL = "https://uat-developer.hdfcsky.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def get_env_file_path() -> str:
    """Returns the absolute path to python/.env."""
    return os.path.join(os.path.dirname(__file__), ".env")


def save_token_to_env(token: str, env_path: str = None) -> bool:
    """
    Saves or updates HDFCSKY_AUTH_TOKEN in the .env file.
    """
    if env_path is None:
        env_path = get_env_file_path()

    try:
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                if line.strip().startswith("HDFCSKY_AUTH_TOKEN="):
                    new_lines.append(f'HDFCSKY_AUTH_TOKEN="{token}"\n')
                    found = True
                else:
                    new_lines.append(line)
            lines = new_lines

        if not found:
            lines.append(f'HDFCSKY_AUTH_TOKEN="{token}"\n')

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        os.environ["HDFCSKY_AUTH_TOKEN"] = token
        return True
    except Exception as e:
        print(f"[!] Warning: Could not write token to .env file: {e}", file=sys.stderr)
        return False


def authorize_with_phone_otp_pass(
    phone_number: str,
    password_or_pin: str,
    otp_callback=None,
    api_key: str = None,
    api_secret: str = None,
    base_url: str = None,
) -> str:
    """
    Executes the 6-step HDFC Sky authorization flow:
    1. Fetch Token ID (GET /oapi/v1/login)
    2. Validate Username / Phone (POST /oapi/v1/login-channel/validate) -> triggers SMS OTP
    3. Validate OTP (PUT /oapi/v1/otp/validate)
    4. Validate PIN/Password (POST /oapi/v1/twofa/validate) -> returns requestToken
    5. Authorize application (GET /oapi/v1/authorise)
    6. Exchange for Access Token (POST /oapi/v1/access-token)
    """
    base_url = (base_url or BASE_URL).rstrip("/")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # Step 1: Fetch Token ID
    print("[1/5] Fetching login session token ID...")
    login_url = f"{base_url}/oapi/v1/login"
    params = {"api_key": api_key} if api_key else {}
    resp = session.get(login_url, params=params, timeout=15)

    if resp.status_code == 401 or "INVALID_APIKEY" in resp.text:
        raise ValueError(
            f"Invalid API Key. Please provide a valid HDFC Sky API Key from https://developer.hdfcsky.com. Response: {resp.text}"
        )
    resp.raise_for_status()

    token_id = resp.json().get("tokenId")
    if not token_id:
        raise ValueError(f"Failed to obtain tokenId from HDFC Sky: {resp.text}")

    # Step 2: Validate Username/Phone to trigger OTP
    print(f"[2/5] Initiating OTP verification for user/phone {phone_number}...")
    validate_url = f"{base_url}/oapi/v1/login-channel/validate"
    val_params = {"api_key": api_key, "token_id": token_id} if api_key else {"token_id": token_id}
    val_resp = session.post(validate_url, params=val_params, json={"username": str(phone_number).strip()}, timeout=15)
    val_resp.raise_for_status()
    val_data = val_resp.json()

    info_msg = val_data.get("message") or "OTP has been sent to your registered mobile and email."
    print(f"      HDFC Sky: {info_msg}")

    # Step 3: Get and validate OTP
    if otp_callback:
        otp = otp_callback()
    else:
        otp = input("👉 Enter the 4 or 6 digit OTP received on your mobile: ").strip()

    if not otp:
        raise ValueError("OTP cannot be empty.")

    print("[3/5] Validating OTP...")
    otp_url = f"{base_url}/oapi/v1/otp/validate"
    otp_params = {"api_key": api_key, "token_id": token_id} if api_key else {"token_id": token_id}
    otp_resp = session.put(otp_url, params=otp_params, json={"otp": str(otp).strip()}, timeout=15)
    otp_resp.raise_for_status()

    # Step 4: Validate 2FA Pin / Password
    print("[4/5] Validating password / PIN...")
    pin_url = f"{base_url}/oapi/v1/twofa/validate"
    pin_params = {"api_key": api_key, "token_id": token_id} if api_key else {"token_id": token_id}
    pin_resp = session.post(pin_url, params=pin_params, json={"answer": str(password_or_pin).strip()}, timeout=15)
    pin_resp.raise_for_status()
    pin_data = pin_resp.json()

    request_token = pin_data.get("requestToken")
    if not request_token:
        raise ValueError(f"Failed to get requestToken after 2FA validation: {pin_resp.text}")

    # Step 5: Authorize application
    print("[5/5] Authorizing and exchanging request token for access token...")
    auth_url = f"{base_url}/oapi/v1/authorise"
    auth_params = {
        "api_key": api_key,
        "token_id": token_id,
        "consent": "true",
        "request_token": request_token,
    }
    auth_resp = session.get(auth_url, params=auth_params, timeout=15)
    auth_resp.raise_for_status()
    auth_data = auth_resp.json()
    final_request_token = auth_data.get("requestToken") or request_token

    # Step 6: Fetch Access Token
    token_url = f"{base_url}/oapi/v1/access-token"
    token_params = {"api_key": api_key, "request_token": final_request_token}
    token_payload = {"apiSecret": api_secret} if api_secret else {}
    token_resp = session.post(token_url, params=token_params, json=token_payload, timeout=15)
    token_resp.raise_for_status()
    token_data = token_resp.json()

    access_token = token_data.get("accessToken") or token_data.get("access_token") or token_data.get("token")
    if not access_token:
        raise ValueError(f"Access token missing in response: {token_resp.text}")

    return access_token


def run_interactive_auth() -> str:
    """
    Guides the user through interactive login:
    - Asks for Phone Number, Password/PIN, API Key/Secret or direct token paste.
    - Saves generated token to python/.env.
    """
    print("\n" + "=" * 55)
    print("🔑 HDFC SKY AUTHENTICATION GENERATOR")
    print("=" * 55)
    print("No active authorization token found in .env.")
    print("Choose an option:")
    print("  [1] Authorize via Phone Number + OTP + PIN/Password (Developer API)")
    print("  [2] Paste an existing x-authorization-token directly")
    print("  [3] Skip (continue with public research feed)")
    print("=" * 55)

    choice = input("Enter choice [1/2/3] (default 1): ").strip() or "1"

    if choice == "2":
        token = input("Paste your x-authorization-token: ").strip().strip("\"'")
        if token:
            save_token_to_env(token)
            print("✅ Token saved to python/.env successfully!\n")
            return token
        else:
            print("[-] No token entered. Skipping.")
            return ""

    elif choice == "3":
        print("[-] Skipping authorization. Monitoring will use public research feed.")
        return ""

    # Option 1: Flow with Phone + OTP + Pass
    phone = os.getenv("HDFCSKY_PHONE")
    if not phone:
        phone = input("👉 Enter your HDFC Sky registered Mobile / Login ID: ").strip()

    api_key = os.getenv("HDFCSKY_API_KEY")
    if not api_key:
        api_key = input("👉 Enter HDFC Sky API Key (from developer.hdfcsky.com): ").strip()

    api_secret = os.getenv("HDFCSKY_API_SECRET")
    if not api_secret:
        api_secret = input("👉 Enter HDFC Sky API Secret: ").strip()

    password = os.getenv("HDFCSKY_PASSWORD")
    if not password:
        password = getpass.getpass("👉 Enter your HDFC Sky PIN / Password: ").strip()

    try:
        token = authorize_with_phone_otp_pass(
            phone_number=phone,
            password_or_pin=password,
            api_key=api_key,
            api_secret=api_secret,
        )
        save_token_to_env(token)
        print("\n🎉 Authorization successful! Generated access token saved to python/.env.")
        return token
    except Exception as e:
        print(f"\n❌ Authorization failed: {e}", file=sys.stderr)
        fallback = input("\nWould you like to paste a session token manually instead? [y/N]: ").strip().lower()
        if fallback == "y":
            manual_token = input("Paste token: ").strip().strip("\"'")
            if manual_token:
                save_token_to_env(manual_token)
                print("✅ Token saved to python/.env successfully!")
                return manual_token
        return ""


if __name__ == "__main__":
    run_interactive_auth()
