#!/usr/bin/env python3
"""
HDFC Sky Live Research & Derivative Recommendation Telegram Monitor
Connects to HDFC Sky's Live API (with automatic public feed fallback)
"""

import os
import sys
import time
import math
import html
import signal
import datetime
import requests

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


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


# ==========================================
# CONFIGURATION
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "6159801726:AAEdnX4VPdT3pxdS7mVgL8bKA7SYsaAJf4w")
CHAT_ID = os.getenv("CHAT_ID", "385686409")

# HDFC Sky Live API Credentials (Optional)
HDFCSKY_AUTH_TOKEN = os.getenv(
    "HDFCSKY_AUTH_TOKEN",
    "eyJhbGciOiJIUzI1NiJ9.eyJkZXZpY2UiOiJ3ZWIiLCJjbGllbnRfaWQiOiJTMzIwMjIwNSIsImNsaWVudF90b2tlbiI6ImRjUUErd1NPbEt6eS92YXRPemV1cG9tNUx2c0RuV1lsZTZvSlRYYVg1T3BVd041K25abng1TFp2ZXM1N3VDZnRVQ2V3bzM5NkVTSVh3YnV5eTA2UkUrZ2tYUTVuN2ZMVDlqQzNMZkVyS1ZSRjRKSXd5RE0rRkZqb2JEN203RURUUmxzamFvWlZLY015RFA3OVhwcnhNcXY5TFQxQ1Y0TUF6SjYwREVrYVYxK0JCdEZPTHNUWXVoU2F3Uk9DTFV1bm5adHZ6QjcvYVZvZkZmMkRYTVA1NWZaVytDbDl0RFIvN2RKVGFGQnlnclE9IiwiZGV2aWNlX2lkIjoiNThiNzgwMjItOWJhMi00NWJmLWFhYjAtNzRjZGE1OTdlY2E2IiwiYmxhY2tsaXN0X2tleSI6IlMzMjAyMjA1OmE2NThhNjFjNTMwNDQyMWZiNWExZDU0MDc2YTlkNjUwIiwiZXhwIjoxNzkxMjcyMzU5MzE2LCJpYXQiOjE3OTExODU5NTl9.mJmS-k7OZmqRKuC629QgsbKkknu8v-AeE1EnDy_Y4us",
)
HDFCSKY_DEVICE_ID = os.getenv("HDFCSKY_DEVICE_ID", "58b78022-9ba2-45bf-aab0-74cda597eca6")

# Endpoints
LIVE_API_OPEN_URL = "https://api.hdfcsky.com/data/api/research/v1/open-calls?category=FNO"
LIVE_API_CLOSED_URL = "https://api.hdfcsky.com/data/api/research/v1/closed-calls?category=FNO"
PUBLIC_API_URL = (
    "https://hdfcsky.com/internal-api/v1/public/get-research-calls"
    "?category=derivatives-recommendations&subcategory=&limit=100"
)

POLL_INTERVAL_SEC = 1.0          # Live check every 1 second
INITIAL_MAX_ALERTS = 10           # Send top 10 on first run
REQUEST_TIMEOUT_SEC = 10.0
TELEGRAM_SEND_DELAY_SEC = 0.35    # Delay to avoid Telegram 429 rate limit

RUNNING = True


# ==========================================
# HELPERS & FORMATTERS
# ==========================================

def log(level: str, message: str, *args):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    extra = (" " + " ".join(str(a) for a in args)) if args else ""
    print(f"[{now}] [{level.upper()}] {message}{extra}", flush=True)


def escape(val) -> str:
    if val is None or val == "":
        return "-"
    return html.escape(str(val))


def format_number(val, decimals: int = 2) -> str:
    if val is None or val == "":
        return "-"
    try:
        num = float(val)
        if num.is_integer():
            return str(int(num))
        return f"{num:.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


def format_currency(val) -> str:
    """Formats a number into standard Indian comma notation (e.g. 22,640.10)."""
    if val is None or val == "":
        return "-"
    try:
        num = float(val)
        is_int = num.is_integer()
        s = f"{int(num)}" if is_int else f"{num:.2f}"
        parts = s.split(".")
        int_part = parts[0]
        dec_part = ("." + parts[1]) if len(parts) > 1 else ""

        is_neg = int_part.startswith("-")
        if is_neg:
            int_part = int_part[1:]

        if len(int_part) <= 3:
            res = int_part
        else:
            last3 = int_part[-3:]
            remaining = int_part[:-3]
            groups = []
            while remaining:
                groups.append(remaining[-2:])
                remaining = remaining[:-2]
            res = ",".join(reversed(groups)) + "," + last3

        return ("-" if is_neg else "") + res + dec_part
    except Exception:
        return str(val)


def format_title_case(val) -> str:
    if not val:
        return "-"
    return str(val).replace("_", " ").title()


def format_telegram_message(call: dict) -> str:
    """
    Formats a recommendation into rich HTML for Telegram:
    - Bold keys (<b>...</b>)
    - Monospace values (<code>...</code>)
    - Collapsible dropdowns (<blockquote expandable>...</blockquote>)
    """
    action = (call.get("transaction") or "buy").upper()
    action_emoji = "🟢" if action == "BUY" else "🔴"

    status = call.get("display_status") or ("OPEN" if call.get("status") == "open" else "CLOSED")
    status_emoji = "🟢"
    if "TARGET" in status.upper() or status == "PROFIT BOOKED":
        status_emoji = "🎯"
    elif "STOPLOSS" in status.upper() or "SL" in status.upper():
        status_emoji = "🛑"
    elif status == "CLOSED":
        status_emoji = "⚪"

    open_price = call.get("open_price")
    target = call.get("target")
    stoploss = call.get("stoploss")
    ltp = call.get("ltp")
    prev_close = call.get("pclose") or call.get("prev_close")

    # 1-Day LTP change
    ltp_change_str = ""
    if ltp and prev_close and prev_close > 0:
        diff = ltp - prev_close
        pct = (diff / prev_close) * 100
        sign = "+" if diff >= 0 else ""
        ltp_change_str = f" ({sign}{format_number(diff)} / {sign}{format_number(pct)}%)"

    # Live P&L from Entry
    live_pnl_str = ""
    if ltp and open_price and open_price > 0:
        if action == "BUY":
            pnl_val = ltp - open_price
            pnl_pct = (pnl_val / open_price) * 100
        else:
            pnl_val = open_price - ltp
            pnl_pct = (pnl_val / open_price) * 100
        pnl_sign = "+" if pnl_val >= 0 else ""
        live_pnl_str = f" ({pnl_sign}{format_number(pnl_pct)}%)"

    # Days remaining to expiry
    now_ms = time.time() * 1000
    expiry_ms = call.get("expiry_date")
    expiry_days = None
    if expiry_ms:
        expiry_days = max(0, math.ceil((expiry_ms - now_ms) / (1000 * 60 * 60 * 24)))

    # Returns / Expected Returns
    returns_str = "-"
    profit = call.get("profit")
    pnl_percentage = call.get("pnl_percentage")
    if profit is not None and profit != 0:
        days_suffix = f" in {expiry_days} days" if expiry_days is not None else ""
        returns_str = f"{format_number(profit)}%{days_suffix}"
    elif pnl_percentage is not None and pnl_percentage != 0:
        sign = "+" if pnl_percentage >= 0 else ""
        returns_str = f"{sign}{format_number(pnl_percentage)}% P&amp;L"

    # Header Profit/Loss Banner
    banner = ""
    call_profit = call.get("call_profit")
    if call_profit is not None and call_profit != 0:
        abs_val = format_number(abs(call_profit))
        if call_profit >= 0:
            banner = f"📈 <b>{abs_val}% Profits in 1 day</b>\n"
        else:
            banner = f"📉 <b>Down by ${abs_val}% in last 1 day</b>\n"

    # Badge / Tag
    tag = call.get("tag")
    tag_line = f"🏷️ <b>{escape(tag.upper())}</b>\n" if tag else ""

    symbol = escape(call.get("symbol"))
    pretty_name = escape(call.get("pretty_name") or call.get("symbol"))

    msg = f"{tag_line}{banner}"
    msg += f"<b>{action_emoji} {action} {symbol}</b>\n"
    msg += f"<i>{pretty_name}</i>\n\n"

    # Key-values: Bold Key & Monospace Value
    msg += f"<b>Reco. Price:</b> <code>₹{format_currency(open_price)}</code>\n"

    target_line = f"<b>Target Price:</b> <code>₹{format_currency(target)}"
    if call.get("target_2"):
        target_line += f" | T2: ₹{format_currency(call.get('target_2'))}"
    target_line += "</code>\n"
    msg += target_line

    msg += f"<b>Stop Loss:</b> <code>₹{format_currency(stoploss)}</code>\n"

    if ltp and ltp > 0:
        msg += f"<b>LTP:</b> <code>₹{format_currency(ltp)}{ltp_change_str}</code>\n"
        msg += f"<b>Live P&amp;L:</b> <code>{live_pnl_str.strip() or '-'}</code>\n"

    msg += f"<b>Returns:</b> <code>{returns_str}</code>\n"
    msg += f"<b>Status:</b> {status_emoji} <code>{escape(status)}</code>\n\n"

    # Expandable dropdown 1: More Trade Info
    details = "<blockquote expandable><b>📊 MORE TRADE INFO</b>\n"
    details += f"<b>Exchange:</b> <code>{escape(str(call.get('exchange') or '').upper())}</code>\n"
    details += f"<b>Segment:</b> <code>{escape(str(call.get('market') or call.get('derivative_source') or '').upper())} • {escape(str(call.get('ins_type') or call.get('type') or '').upper())}</code>\n"
    if call.get("token"):
        details += f"<b>Token:</b> <code>{call.get('token')}</code>\n"
    if call.get("lot_size"):
        details += f"<b>Lot Size:</b> <code>{call.get('lot_size')}</code>\n"
    if call.get("horizon"):
        details += f"<b>Horizon:</b> <code>{escape(format_title_case(call.get('horizon')))}</code>\n"
    if call.get("order_type"):
        details += f"<b>Order Type:</b> <code>{escape(format_title_case(call.get('order_type')).upper())}</code>\n"
    if call.get("lower_dip_price") and call.get("lower_dip_price") > 0:
        details += f"<b>Add on Dips:</b> <code>₹{format_currency(call.get('lower_dip_price'))} ({escape(call.get('dip_status') or 'Active')})</code>\n"
    if prev_close and prev_close > 0:
        details += f"<b>Prev. Close:</b> <code>₹{format_currency(prev_close)}</code>\n"
    if call.get("validity"):
        val_ms = call.get("validity")
        val_date = datetime.datetime.fromtimestamp(val_ms / 1000, tz=datetime.timezone.utc).strftime("%d %b %Y")
        details += f"<b>Validity:</b> <code>{val_date}</code>\n"
    if call.get("closed_price"):
        details += f"<b>Closed Price:</b> <code>₹{format_currency(call.get('closed_price'))}</code>\n"
    if call.get("report_url"):
        details += f'<b>Report:</b> <a href="{escape(call.get("report_url"))}">Download PDF</a>\n'
    details += "</blockquote>\n\n"
    msg += details

    # Expandable dropdown 2: Analyst Note
    if call.get("call_message"):
        msg += f"<blockquote expandable><b>📝 ANALYST NOTE</b>\n<i>{escape(call.get('call_message'))}</i></blockquote>\n\n"

    if call.get("url"):
        msg += f'<a href="{escape(call.get("url"))}">🔗 View on HDFC Sky</a>'

    return msg


# ==========================================
# TELEGRAM SENDER (With Rate Limit Handling)
# ==========================================

def send_telegram_message(session: requests.Session, text: str, max_retries: int = 3) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(url, json=payload, timeout=REQUEST_TIMEOUT_SEC)
            data = {}
            try:
                data = resp.json()
            except Exception:
                pass

            if resp.ok and data.get("ok"):
                return True

            # Handle Telegram 429 Too Many Requests
            if resp.status_code == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 2)
                log("warn", f"Telegram 429: Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after + 1)
                continue

            log("error", f"Telegram API response (attempt {attempt}/{max_retries}):", data.get("description", resp.text))
        except Exception as e:
            log("error", f"Telegram network error (attempt {attempt}/{max_retries}):", str(e))

        if attempt < max_retries:
            time.sleep(1.0 * attempt)

    return False


# ==========================================
# HDFC SKY API FETCH & PARSE (LIVE + FALLBACK)
# ==========================================

def fetch_live_api(session: requests.Session) -> dict:
    """Fetches live real-time recommendations directly from api.hdfcsky.com."""
    headers = {
        "accept": "application/json, text/plain, */*",
        "origin": "https://hdfcsky.com",
        "referer": "https://hdfcsky.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        ),
        "x-app-ver": "6.47.0",
        "x-authorization-token": HDFCSKY_AUTH_TOKEN,
        "Authorization": HDFCSKY_AUTH_TOKEN,
        "x-device-id": HDFCSKY_DEVICE_ID,
        "x-device-make": "Desktop",
        "x-device-model": "Chrome 154",
        "x-device-os": "Windows",
        "x-device-type": "web",
    }

    resp = session.get(LIVE_API_OPEN_URL, headers=headers, timeout=REQUEST_TIMEOUT_SEC)

    if resp.status_code == 401:
        raise PermissionError("401 Unauthorized: HDFCSKY_AUTH_TOKEN has expired or is invalid.")

    resp.raise_for_status()
    data = resp.json().get("data", [])
    calls_map = {}

    for group in data:
        for call in group.get("calls", []):
            call_id = call.get("id")
            if not call_id:
                continue

            calls_map[call_id] = {
                "id": call_id,
                "title": call.get("pretty_name") or call.get("name") or call.get("symbol"),
                "symbol": call.get("symbol") or "-",
                "exchange": call.get("exchange") or "nse",
                "type": call.get("ins_type") or "-",
                "market": call.get("derivative_source") or "FNO",
                "strike": call.get("strike_price") if call.get("strike_price") is not None else "-",
                "transaction": call.get("transaction") or "buy",
                "tag": call.get("tag") or "",
                "status": "open",
                "display_status": "OPEN",
                "open_price": call.get("open_price") or call.get("call_open_price"),
                "target": call.get("target"),
                "target_2": call.get("target_2"),
                "stoploss": call.get("stoploss"),
                "ltp": call.get("ltp"),
                "pclose": call.get("pclose"),
                "prev_close": call.get("pclose"),
                "token": call.get("token"),
                "validity": call.get("validity"),
                "creation_time": call.get("creation_time") or call.get("openDate"),
                "last_updated_time": call.get("currentDate") or call.get("creation_time") or 0,
                "report_url": call.get("report_url"),
                "derivative_source": call.get("derivative_source"),
                "pretty_name": call.get("pretty_name") or call.get("name") or "",
                "url": "https://hdfcsky.com/research",
            }

    # Also fetch recent closed calls to populate initial feed
    try:
        resp_closed = session.get(LIVE_API_CLOSED_URL, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
        if resp_closed.ok:
            closed_list = resp_closed.json().get("data", {}).get("closeCall", [])
            for call in closed_list:
                call_id = call.get("id")
                if not call_id or call_id in calls_map:
                    continue

                calls_map[call_id] = {
                    "id": call_id,
                    "title": call.get("pretty_name") or call.get("name") or call.get("symbol"),
                    "symbol": call.get("symbol") or "-",
                    "exchange": call.get("exchange") or "nse",
                    "type": call.get("ins_type") or "-",
                    "market": call.get("derivative_source") or "FNO",
                    "strike": call.get("strike_price") if call.get("strike_price") is not None else "-",
                    "transaction": call.get("transaction") or "buy",
                    "tag": call.get("tag") or "",
                    "status": "closed",
                    "display_status": call.get("display_status") or "CLOSED",
                    "open_price": call.get("open_price") or call.get("call_open_price"),
                    "target": call.get("target"),
                    "target_2": call.get("target_2"),
                    "stoploss": call.get("stoploss"),
                    "ltp": call.get("ltp") or 0,
                    "pclose": call.get("pclose") or 0,
                    "prev_close": call.get("pclose") or 0,
                    "token": call.get("token"),
                    "validity": call.get("validity"),
                    "pnl_percentage": call.get("pnl_percentage") or 0,
                    "closed_by": call.get("closed_by"),
                    "creation_time": call.get("creation_time") or call.get("openDate"),
                    "last_updated_time": call.get("last_updated_time") or call.get("creation_time") or 0,
                    "report_url": call.get("report_url"),
                    "derivative_source": call.get("derivative_source"),
                    "pretty_name": call.get("pretty_name") or call.get("name") or "",
                    "url": "https://hdfcsky.com/research",
                }
    except Exception as e:
        log("debug", f"Optional closed calls fetch notice: {e}")

    return calls_map


def fetch_public_fallback(session: requests.Session) -> dict:
    """Fallback fetcher using public research calls endpoint."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://hdfcsky.com/research",
    }

    resp = session.get(PUBLIC_API_URL, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()

    data = resp.json().get("data", {})
    documents = data.get("documents", [])
    calls_map = {}

    for doc in documents:
        val = doc.get("value", {}) or {}
        calls = val.get("all_calls", []) or []
        permalink = ("https://hdfcsky.com" + val.get("permalink")) if val.get("permalink") else ""

        for call in calls:
            call_id = call.get("id")
            if not call_id:
                continue

            calls_map[call_id] = {
                "id": call_id,
                "title": call.get("pretty_name") or val.get("title") or call.get("symbol") or "New Recommendation",
                "symbol": call.get("symbol") or "-",
                "exchange": call.get("exchange") or "-",
                "type": call.get("ins_type") or "-",
                "market": call.get("market") or "-",
                "strike": call.get("strike_price") if call.get("strike_price") is not None else "-",
                "transaction": call.get("transaction") or "buy",
                "tag": call.get("tag") or "",
                "status": call.get("status") or "open",
                "display_status": call.get("display_status"),
                "open_price": call.get("open_price"),
                "target": call.get("target"),
                "target_2": call.get("target_2"),
                "stoploss": call.get("stoploss"),
                "horizon": call.get("horizon") or "-",
                "research_type": call.get("research_type") or "-",
                "call_message": call.get("call_message") or "",
                "ltp": call.get("ltp") or 0,
                "prev_close": call.get("prev_close") or 0,
                "profit": call.get("profit") or 0,
                "call_profit": call.get("call_profit") or 0,
                "pnl": call.get("pnl") or 0,
                "pnl_percentage": call.get("pnl_percentage") or 0,
                "open_time": call.get("open_time") or 0,
                "last_updated_time": call.get("last_updated_time") or call.get("open_time") or 0,
                "expiry_date": call.get("expiry_date"),
                "validity": call.get("validity"),
                "lot_size": call.get("lot_size"),
                "order_type": call.get("order_type"),
                "lower_dip_price": call.get("lower_dip_price"),
                "dip_status": call.get("dip_status"),
                "order_value": call.get("order_value"),
                "order_count": call.get("order_count"),
                "unique_client_order_count": call.get("unique_client_order_count"),
                "closed_price": call.get("closed_price"),
                "pretty_name": call.get("pretty_name") or "",
                "url": permalink,
            }

    return calls_map


def fetch_recommendations(session: requests.Session) -> dict:
    """Smart router: uses Live HDFC Sky API when token is active, falls back to public API seamlessly."""
    if HDFCSKY_AUTH_TOKEN:
        try:
            return fetch_live_api(session)
        except PermissionError as pe:
            log("warn", str(pe))
            log("warn", "Seamlessly switching to public research feed...")
        except Exception as e:
            log("warn", f"Live API issue ({e}). Falling back to public research feed...")

    return fetch_public_fallback(session)


def ensure_auth_token():
    """Checks if HDFCSKY_AUTH_TOKEN is present; if missing and running in interactive console, prompts to generate one."""
    global HDFCSKY_AUTH_TOKEN
    if not HDFCSKY_AUTH_TOKEN:
        log("warn", "No HDFCSKY_AUTH_TOKEN found in environment or .env.")
        if sys.stdin and sys.stdin.isatty():
            try:
                log("info", "Starting interactive authorization helper...")
                from auth import run_interactive_auth
                token = run_interactive_auth()
                if token:
                    HDFCSKY_AUTH_TOKEN = token
                    os.environ["HDFCSKY_AUTH_TOKEN"] = token
                    log("info", "Successfully generated and applied new auth token!")
            except Exception as e:
                log("error", f"Authorization helper error: {e}")
                log("info", "Falling back to public research feed.")
        else:
            log("info", "Non-interactive session. Using public research feed fallback.")


# ==========================================
# MONITOR DAEMON (1-SECOND LOOP)
# ==========================================

def start_monitor():
    global RUNNING

    ensure_auth_token()

    log("info", "=" * 50)
    log("info", "HDFC SKY LIVE RECOMMENDATION MONITOR (Python)")
    log("info", f"Polling Interval: {POLL_INTERVAL_SEC}s")
    log("info", f"Initial Alert Count: Top {INITIAL_MAX_ALERTS} recommendations")
    log("info", f"Mode: {'Live Trading API' if HDFCSKY_AUTH_TOKEN else 'Public Research Feed'}")
    log("info", "=" * 50)

    previous_calls = {}
    is_first_run = True
    consecutive_errors = 0

    session = requests.Session()

    while RUNNING:
        start_time = time.time()

        try:
            current_calls = fetch_recommendations(session)
            consecutive_errors = 0

            if is_first_run:
                log("info", f"First run: Loaded {len(current_calls)} recommendations.")

                all_list = list(current_calls.values())
                initial_to_send = all_list[:INITIAL_MAX_ALERTS]

                log("info", f"Sending top {len(initial_to_send)} cards to Telegram...")

                for call in initial_to_send:
                    action = call.get("transaction", "buy").upper()
                    log("info", f"[FIRST RUN] {action} {call.get('symbol')} - {call.get('title')}")
                    send_telegram_message(session, format_telegram_message(call))
                    time.sleep(TELEGRAM_SEND_DELAY_SEC)

                previous_calls = current_calls
                is_first_run = False
                log("info", "Startup complete. Monitoring for new recommendations or updates every 1s...")
            else:
                updates_to_send = []

                for call_id, call in current_calls.items():
                    prev = previous_calls.get(call_id)

                    if not prev:
                        # Brand new recommendation
                        updates_to_send.append(("NEW", call))
                    elif (
                        call["last_updated_time"] > prev["last_updated_time"]
                        or call["status"] != prev["status"]
                        or call["display_status"] != prev["display_status"]
                    ):
                        # Modified call or status change (e.g. Target Achieved / Stop Loss Hit)
                        updates_to_send.append(("UPDATE", call))

                if updates_to_send:
                    log("info", f"Detected {len(updates_to_send)} update(s)!")

                    for tag, call in updates_to_send:
                        action = call.get("transaction", "buy").upper()
                        status_label = call.get("display_status") or tag
                        log("info", f"[{status_label}] {action} {call.get('symbol')} ({call.get('id')})")
                        send_telegram_message(session, format_telegram_message(call))
                        time.sleep(TELEGRAM_SEND_DELAY_SEC)

                previous_calls = current_calls

        except Exception as e:
            consecutive_errors += 1
            backoff_sec = min(2**consecutive_errors, 30)
            log("error", f"Fetch failed: {e}. Retrying in {backoff_sec}s...")
            time.sleep(backoff_sec)

        elapsed = time.time() - start_time
        remaining = max(0.0, POLL_INTERVAL_SEC - elapsed)
        if RUNNING and remaining > 0:
            time.sleep(remaining)

    log("info", "Monitor loop stopped cleanly.")


def handle_exit(signum, frame):
    global RUNNING
    log("info", "Received termination signal. Shutting down...")
    RUNNING = False


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

if __name__ == "__main__":
    start_monitor()
