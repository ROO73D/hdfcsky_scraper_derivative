/**
 * HDFC Sky Live Research Recommendation Telegram Monitor
 * Pure Node.js 24/7 Background Daemon (1-second polling)
 * Connects to HDFC Sky's Live API (with automatic public feed fallback)
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Built-in .env loader (zero external dependencies)
function loadEnv() {
  const envPath = path.join(__dirname, ".env");
  if (fs.existsSync(envPath)) {
    try {
      const content = fs.readFileSync(envPath, "utf-8");
      for (const line of content.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith("#") && trimmed.includes("=")) {
          const idx = trimmed.indexOf("=");
          const key = trimmed.slice(0, idx).trim();
          const val = trimmed.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
          if (key && !process.env[key]) {
            process.env[key] = val;
          }
        }
      }
    } catch {}
  }
}
loadEnv();

// ==========================================
// CONFIGURATION
// ==========================================
const BOT_TOKEN = process.env.BOT_TOKEN || "6159801726:AAEdnX4VPdT3pxdS7mVgL8bKA7SYsaAJf4w";
const CHAT_ID = process.env.CHAT_ID || "385686409";

const HDFCSKY_AUTH_TOKEN =
  process.env.HDFCSKY_AUTH_TOKEN ||
  "eyJhbGciOiJIUzI1NiJ9.eyJkZXZpY2UiOiJ3ZWIiLCJjbGllbnRfaWQiOiJTMzIwMjIwNSIsImNsaWVudF90b2tlbiI6ImRjUUErd1NPbEt6eS92YXRPemV1cG9tNUx2c0RuV1lsZTZvSlRYYVg1T3BVd041K25abng1TFp2ZXM1N3VDZnRVQ2V3bzM5NkVTSVh3YnV5eTA2UkUrZ2tYUTVuN2ZMVDlqQzNMZkVyS1ZSRjRKSXd5RE0rRkZqb2JEN203RURUUmxzamFvWlZLY015RFA3OVhwcnhNcXY5TFQxQ1Y0TUF6SjYwREVrYVYxK0JCdEZPTHNUWXVoU2F3Uk9DTFV1bm5adHZ6QjcvYVZvZkZmMkRYTVA1NWZaVytDbDl0RFIvN2RKVGFGQnlnclE9IiwiZGV2aWNlX2lkIjoiNThiNzgwMjItOWJhMi00NWJmLWFhYjAtNzRjZGE1OTdlY2E2IiwiYmxhY2tsaXN0X2tleSI6IlMzMjAyMjA1OmE2NThhNjFjNTMwNDQyMWZiNWExZDU0MDc2YTlkNjUwIiwiZXhwIjoxNzkxMjcyMzU5MzE2LCJpYXQiOjE3OTExODU5NTl9.mJmS-k7OZmqRKuC629QgsbKkknu8v-AeE1EnDy_Y4us";
const HDFCSKY_DEVICE_ID = process.env.HDFCSKY_DEVICE_ID || "58b78022-9ba2-45bf-aab0-74cda597eca6";

// Endpoints
const LIVE_API_OPEN_URL = "https://api.hdfcsky.com/data/api/research/v1/open-calls?category=FNO";
const LIVE_API_CLOSED_URL = "https://api.hdfcsky.com/data/api/research/v1/closed-calls?category=FNO";
const PUBLIC_API_URL =
  "https://hdfcsky.com/internal-api/v1/public/get-research-calls?category=derivatives-recommendations&subcategory=&limit=100";

const POLL_INTERVAL_MS = 1000;       // Live check every 1 second
const INITIAL_MAX_ALERTS = 10;        // Broadcast top 10 on first run
const REQUEST_TIMEOUT_MS = 10000;
const TELEGRAM_SEND_DELAY_MS = 350;   // Delay to avoid Telegram 429 rate limits

// ==========================================
// HELPERS & FORMATTERS
// ==========================================

function log(level, message, ...args) {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`, ...args);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function escapeHtml(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatNumber(val, decimals = 2) {
  if (val === null || val === undefined || isNaN(val)) return "-";
  const num = Number(val);
  return Number.isInteger(num) ? String(num) : num.toFixed(decimals);
}

function formatCurrency(val) {
  if (val === null || val === undefined || isNaN(val)) return "-";
  return Number(val).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: Number.isInteger(Number(val)) ? 0 : 2,
  });
}

function formatTitleCase(str) {
  if (!str) return "-";
  return String(str)
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Formats a recommendation into rich HTML for Telegram:
 * - Bold keys (<b>...</b>)
 * - Monospace values (<code>...</code>)
 * - Collapsible dropdowns (<blockquote expandable>...</blockquote>)
 */
function formatTelegramMessage(call) {
  const action = (call.transaction || "buy").toUpperCase();
  const actionEmoji = action === "BUY" ? "🟢" : "🔴";

  const status = call.display_status || (call.status === "open" ? "OPEN" : "CLOSED");
  let statusEmoji = "🟢";
  const upperStatus = status.toUpperCase();
  if (upperStatus.includes("TARGET") || status === "PROFIT BOOKED") {
    statusEmoji = "🎯";
  } else if (upperStatus.includes("STOPLOSS") || upperStatus.includes("SL")) {
    statusEmoji = "🛑";
  } else if (status === "CLOSED") {
    statusEmoji = "⚪";
  }

  const openPrice = call.open_price;
  const target = call.target;
  const stoploss = call.stoploss;
  const ltp = call.ltp;
  const prevClose = call.pclose || call.prev_close;

  // 1-Day LTP change
  let ltpChangeStr = "";
  if (ltp && prevClose && prevClose > 0) {
    const diff = ltp - prevClose;
    const pct = (diff / prevClose) * 100;
    const sign = diff >= 0 ? "+" : "";
    ltpChangeStr = ` (${sign}${formatNumber(diff)} / ${sign}${formatNumber(pct)}%)`;
  }

  // Live P&L from Entry
  let livePnlStr = "";
  if (ltp && openPrice && openPrice > 0) {
    const diff = action === "BUY" ? ltp - openPrice : openPrice - ltp;
    const pct = (diff / openPrice) * 100;
    const sign = diff >= 0 ? "+" : "";
    livePnlStr = ` (${sign}${formatNumber(pct)}%)`;
  }

  // Days remaining to expiry
  const now = Date.now();
  const expiryDays = call.expiry_date
    ? Math.max(0, Math.ceil((call.expiry_date - now) / (1000 * 60 * 60 * 24)))
    : null;

  // Expected returns / Returns
  let returnsStr = "-";
  if (call.profit !== undefined && call.profit !== null && call.profit !== 0) {
    returnsStr = `${formatNumber(call.profit)}%${expiryDays !== null ? ` in ${expiryDays} days` : ""}`;
  } else if (call.pnl_percentage !== undefined && call.pnl_percentage !== null && call.pnl_percentage !== 0) {
    const sign = call.pnl_percentage >= 0 ? "+" : "";
    returnsStr = `${sign}${formatNumber(call.pnl_percentage)}% P&amp;L`;
  }

  // Header Banner: Profit or Down by
  let banner = "";
  if (call.call_profit !== undefined && call.call_profit !== null && call.call_profit !== 0) {
    const absVal = formatNumber(Math.abs(call.call_profit));
    if (call.call_profit >= 0) {
      banner = `📈 <b>${absVal}% Profits in 1 day</b>\n`;
    } else {
      banner = `📉 <b>Down by ${absVal}% in last 1 day</b>\n`;
    }
  }

  const tagLine = call.tag ? `🏷️ <b>${escapeHtml(call.tag.toUpperCase())}</b>\n` : "";

  let msg = `${tagLine}${banner}`;
  msg += `<b>${actionEmoji} ${action} ${escapeHtml(call.symbol)}</b>\n`;
  msg += `<i>${escapeHtml(call.pretty_name || call.symbol)}</i>\n\n`;

  // Key-values: Bold Key & Monospace Value
  msg += `<b>Reco. Price:</b> <code>₹${formatCurrency(openPrice)}</code>\n`;
  msg += `<b>Target Price:</b> <code>₹${formatCurrency(target)}`;
  if (call.target_2) msg += ` | T2: ₹${formatCurrency(call.target_2)}`;
  msg += `</code>\n`;
  msg += `<b>Stop Loss:</b> <code>₹${formatCurrency(stoploss)}</code>\n`;

  if (ltp && ltp > 0) {
    msg += `<b>LTP:</b> <code>₹${formatCurrency(ltp)}${ltpChangeStr}</code>\n`;
    msg += `<b>Live P&amp;L:</b> <code>${livePnlStr.trim() || "-"}</code>\n`;
  }

  msg += `<b>Returns:</b> <code>${returnsStr}</code>\n`;
  msg += `<b>Status:</b> ${statusEmoji} <code>${escapeHtml(status)}</code>\n\n`;

  // Expandable dropdown 1: More Trade Info
  let details = `<blockquote expandable><b>📊 MORE TRADE INFO</b>\n`;
  details += `<b>Exchange:</b> <code>${escapeHtml(call.exchange?.toUpperCase())}</code>\n`;
  details += `<b>Segment:</b> <code>${escapeHtml((call.market || call.derivative_source)?.toUpperCase())} • ${escapeHtml((call.type || call.ins_type)?.toUpperCase())}</code>\n`;
  if (call.token) {
    details += `<b>Token:</b> <code>${call.token}</code>\n`;
  }
  if (call.lot_size) {
    details += `<b>Lot Size:</b> <code>${call.lot_size}</code>\n`;
  }
  if (call.horizon) {
    details += `<b>Horizon:</b> <code>${escapeHtml(formatTitleCase(call.horizon))}</code>\n`;
  }
  if (call.order_type) {
    details += `<b>Order Type:</b> <code>${escapeHtml(formatTitleCase(call.order_type).toUpperCase())}</code>\n`;
  }
  if (call.lower_dip_price && call.lower_dip_price > 0) {
    details += `<b>Add on Dips:</b> <code>₹${formatCurrency(call.lower_dip_price)} (${escapeHtml(call.dip_status || "Active")})</code>\n`;
  }
  if (prevClose && prevClose > 0) {
    details += `<b>Prev. Close:</b> <code>₹${formatCurrency(prevClose)}</code>\n`;
  }
  if (call.validity) {
    const valDate = new Date(call.validity).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    details += `<b>Validity:</b> <code>${valDate}</code>\n`;
  }
  if (call.closed_price) {
    details += `<b>Closed Price:</b> <code>₹${formatCurrency(call.closed_price)}</code>\n`;
  }
  if (call.report_url) {
    details += `<b>Report:</b> <a href="${escapeHtml(call.report_url)}">Download PDF</a>\n`;
  }
  details += `</blockquote>\n\n`;
  msg += details;

  // Expandable dropdown 2: Analyst Note
  if (call.call_message) {
    msg += `<blockquote expandable><b>📝 ANALYST NOTE</b>\n<i>${escapeHtml(call.call_message)}</i></blockquote>\n\n`;
  }

  if (call.url) {
    msg += `<a href="${escapeHtml(call.url)}">🔗 View on HDFC Sky</a>`;
  }

  return msg;
}

// ==========================================
// TELEGRAM SENDER (With Retry & Rate Limits)
// ==========================================

async function sendTelegramMessage(text, maxRetries = 3) {
  const url = `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`;
  const payload = {
    chat_id: CHAT_ID,
    text: text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });

      const data = await response.json().catch(() => ({}));

      if (response.ok && data.ok) {
        return true;
      }

      if (response.status === 429 && data.parameters?.retry_after) {
        const retryAfter = data.parameters.retry_after;
        log("warn", `Telegram 429: Rate limited. Waiting ${retryAfter}s...`);
        await sleep((retryAfter + 1) * 1000);
        continue;
      }

      log("error", `Telegram API response (attempt ${attempt}/${maxRetries}):`, data.description || response.statusText);
    } catch (err) {
      log("error", `Telegram network error (attempt ${attempt}/${maxRetries}):`, err.message);
    }

    if (attempt < maxRetries) {
      await sleep(1000 * attempt);
    }
  }

  return false;
}

// ==========================================
// HDFC SKY LIVE API FETCH (WITH FALLBACK)
// ==========================================

async function fetchLiveApi() {
  const headers = {
    accept: "application/json, text/plain, */*",
    origin: "https://hdfcsky.com",
    referer: "https://hdfcsky.com/",
    "user-agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "x-app-ver": "6.47.0",
    "x-authorization-token": HDFCSKY_AUTH_TOKEN,
    "x-device-id": HDFCSKY_DEVICE_ID,
    "x-device-make": "Desktop",
    "x-device-model": "Chrome 154",
    "x-device-os": "Windows",
    "x-device-type": "web",
  };

  const response = await fetch(LIVE_API_OPEN_URL, {
    method: "GET",
    headers,
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (response.status === 401) {
    throw new Error("401 Unauthorized: HDFCSKY_AUTH_TOKEN has expired or is invalid.");
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const json = await response.json();
  const groups = json?.data || [];
  const callsMap = new Map();

  for (const group of groups) {
    for (const call of group.calls || []) {
      const callId = call.id;
      if (!callId) continue;

      callsMap.set(callId, {
        id: callId,
        title: call.pretty_name || call.name || call.symbol,
        symbol: call.symbol || "-",
        exchange: call.exchange || "nse",
        type: call.ins_type || "-",
        market: call.derivative_source || "FNO",
        strike: call.strike_price ?? "-",
        transaction: call.transaction || "buy",
        tag: call.tag || "",
        status: "open",
        display_status: "OPEN",
        open_price: call.open_price || call.call_open_price,
        target: call.target,
        target_2: call.target_2,
        stoploss: call.stoploss,
        ltp: call.ltp,
        pclose: call.pclose,
        prev_close: call.pclose,
        token: call.token,
        validity: call.validity,
        creation_time: call.creation_time || call.openDate,
        last_updated_time: call.currentDate || call.creation_time || 0,
        report_url: call.report_url,
        derivative_source: call.derivative_source,
        pretty_name: call.pretty_name || call.name || "",
        url: "https://hdfcsky.com/research",
      });
    }
  }

  // Also fetch closed calls for initial view
  try {
    const resClosed = await fetch(LIVE_API_CLOSED_URL, {
      method: "GET",
      headers,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (resClosed.ok) {
      const jsonClosed = await resClosed.json();
      const closedCalls = jsonClosed?.data?.closeCall || [];
      for (const call of closedCalls) {
        const callId = call.id;
        if (!callId || callsMap.has(callId)) continue;

        callsMap.set(callId, {
          id: callId,
          title: call.pretty_name || call.name || call.symbol,
          symbol: call.symbol || "-",
          exchange: call.exchange || "nse",
          type: call.ins_type || "-",
          market: call.derivative_source || "FNO",
          strike: call.strike_price ?? "-",
          transaction: call.transaction || "buy",
          tag: call.tag || "",
          status: "closed",
          display_status: call.display_status || "CLOSED",
          open_price: call.open_price || call.call_open_price,
          target: call.target,
          target_2: call.target_2,
          stoploss: call.stoploss,
          ltp: call.ltp || 0,
          pclose: call.pclose || 0,
          prev_close: call.pclose || 0,
          token: call.token,
          validity: call.validity,
          pnl_percentage: call.pnl_percentage || 0,
          closed_by: call.closed_by,
          creation_time: call.creation_time || call.openDate,
          last_updated_time: call.last_updated_time || call.creation_time || 0,
          report_url: call.report_url,
          derivative_source: call.derivative_source,
          pretty_name: call.pretty_name || call.name || "",
          url: "https://hdfcsky.com/research",
        });
      }
    }
  } catch (e) {
    // Non-fatal
  }

  return callsMap;
}

async function fetchPublicFallback() {
  const response = await fetch(PUBLIC_API_URL, {
    method: "GET",
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
      Accept: "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9",
      Referer: "https://hdfcsky.com/research",
    },
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
  }

  const json = await response.json();
  const documents = json?.data?.documents || [];
  const callsMap = new Map();

  for (const doc of documents) {
    const value = doc.value || {};
    const calls = value.all_calls || [];
    const permalink = value.permalink ? `https://hdfcsky.com${value.permalink}` : "";

    for (const call of calls) {
      const callId = call.id;
      if (!callId) continue;

      callsMap.set(callId, {
        id: callId,
        title: call.pretty_name || value.title || call.symbol || "New Recommendation",
        symbol: call.symbol || "-",
        exchange: call.exchange || "-",
        type: call.ins_type || "-",
        market: call.market || "-",
        strike: call.strike_price ?? "-",
        transaction: call.transaction || "buy",
        tag: call.tag || "",
        status: call.status || "open",
        display_status: call.display_status || null,
        open_price: call.open_price ?? "-",
        target: call.target ?? "-",
        target_2: call.target_2 ?? null,
        stoploss: call.stoploss ?? "-",
        horizon: call.horizon || "-",
        research_type: call.research_type || "-",
        call_message: call.call_message || "",
        ltp: call.ltp ?? 0,
        prev_close: call.prev_close ?? 0,
        profit: call.profit ?? 0,
        call_profit: call.call_profit ?? 0,
        pnl: call.pnl ?? 0,
        pnl_percentage: call.pnl_percentage ?? 0,
        open_time: call.open_time || 0,
        last_updated_time: call.last_updated_time || call.open_time || 0,
        expiry_date: call.expiry_date || null,
        validity: call.validity || null,
        lot_size: call.lot_size || null,
        order_type: call.order_type || null,
        lower_dip_price: call.lower_dip_price || null,
        dip_status: call.dip_status || null,
        order_value: call.order_value || null,
        order_count: call.order_count || null,
        unique_client_order_count: call.unique_client_order_count || null,
        closed_price: call.closed_price || null,
        pretty_name: call.pretty_name || "",
        url: permalink,
      });
    }
  }

  return callsMap;
}

async function fetchRecommendations() {
  if (HDFCSKY_AUTH_TOKEN) {
    try {
      return await fetchLiveApi();
    } catch (err) {
      log("warn", `Live API issue: ${err.message}. Seamlessly falling back to public feed...`);
    }
  }
  return await fetchPublicFallback();
}

// ==========================================
// MONITOR DAEMON (1-SECOND LOOP)
// ==========================================

let isRunning = true;

async function startMonitor() {
  log("info", "=".repeat(50));
  log("info", "HDFC SKY LIVE RECOMMENDATION MONITOR (Node.js)");
  log("info", `Polling Interval: ${POLL_INTERVAL_MS}ms`);
  log("info", `Initial Alert Count: Top ${INITIAL_MAX_ALERTS} recommendations`);
  log("info", `Mode: ${HDFCSKY_AUTH_TOKEN ? "Live Trading API" : "Public Research Feed"}`);
  log("info", "=".repeat(50));

  let previousCalls = new Map();
  let isFirstRun = true;
  let consecutiveErrors = 0;

  while (isRunning) {
    const startTime = Date.now();

    try {
      const currentCalls = await fetchRecommendations();
      consecutiveErrors = 0;

      if (isFirstRun) {
        log("info", `First run: Loaded ${currentCalls.size} recommendations.`);

        const allList = Array.from(currentCalls.values());
        const initialToSend = allList.slice(0, INITIAL_MAX_ALERTS);

        log("info", `Sending top ${initialToSend.length} cards to Telegram...`);

        for (const call of initialToSend) {
          log("info", `[FIRST RUN] ${call.transaction.toUpperCase()} ${call.symbol} - ${call.title}`);
          await sendTelegramMessage(formatTelegramMessage(call));
          await sleep(TELEGRAM_SEND_DELAY_MS);
        }

        previousCalls = currentCalls;
        isFirstRun = false;
        log("info", `Startup complete. Monitoring for new recommendations or updates every 1s...`);
      } else {
        const updatesToSend = [];

        for (const [callId, call] of currentCalls.entries()) {
          const prev = previousCalls.get(callId);

          if (!prev) {
            updatesToSend.push({ type: "NEW", call });
          } else if (
            call.last_updated_time > prev.last_updated_time ||
            call.status !== prev.status ||
            call.display_status !== prev.display_status
          ) {
            updatesToSend.push({ type: "UPDATE", call });
          }
        }

        if (updatesToSend.length > 0) {
          log("info", `Detected ${updatesToSend.length} update(s)!`);

          for (const item of updatesToSend) {
            const statusLabel = item.call.display_status || item.type;
            log("info", `[${statusLabel}] ${item.call.transaction.toUpperCase()} ${item.call.symbol} (${item.call.id})`);
            await sendTelegramMessage(formatTelegramMessage(item.call));
            await sleep(TELEGRAM_SEND_DELAY_MS);
          }
        }

        previousCalls = currentCalls;
      }
    } catch (err) {
      consecutiveErrors++;
      const backoffSec = Math.min(Math.pow(2, consecutiveErrors), 30);
      log("error", `Fetch failed: ${err.message}. Retrying in ${backoffSec}s...`);
      await sleep(backoffSec * 1000);
    }

    const elapsedTime = Date.now() - startTime;
    const remainingDelay = Math.max(0, POLL_INTERVAL_MS - elapsedTime);

    if (isRunning && remainingDelay > 0) {
      await sleep(remainingDelay);
    }
  }

  log("info", "Monitor loop stopped cleanly.");
}

// Graceful termination handling
process.on("SIGINT", () => {
  log("info", "Stopping monitor (SIGINT)...");
  isRunning = false;
  setTimeout(() => process.exit(0), 1000);
});

process.on("SIGTERM", () => {
  log("info", "Stopping monitor (SIGTERM)...");
  isRunning = false;
  setTimeout(() => process.exit(0), 1000);
});

// Run directly
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/"))) {
  startMonitor().catch((err) => {
    log("error", "Fatal error:", err);
    process.exit(1);
  });
}

export {
  BOT_TOKEN,
  CHAT_ID,
  HDFCSKY_AUTH_TOKEN,
  HDFCSKY_DEVICE_ID,
  fetchRecommendations,
  fetchLiveApi,
  fetchPublicFallback,
  formatTelegramMessage,
  escapeHtml,
  sendTelegramMessage,
  startMonitor,
};
