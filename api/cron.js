import {
  BOT_TOKEN,
  CHAT_ID,
  fetchRecommendations,
  formatTelegramMessage,
  sendTelegramMessage,
} from "../js/bot.js";

// In-memory cache for warm Vercel serverless isolates
let cachedCalls = new Map();
let isFirstExecution = true;

export default async function handler(req, res) {
  try {
    const currentCalls = await fetchRecommendations();
    let sentCount = 0;

    if (isFirstExecution || cachedCalls.size === 0) {
      // First run: broadcast up to 10 latest
      const allList = Array.from(currentCalls.values());
      const initialToSend = allList.slice(0, 10);

      for (const call of initialToSend) {
        await sendTelegramMessage(formatTelegramMessage(call));
        sentCount++;
      }

      cachedCalls = currentCalls;
      isFirstExecution = false;
    } else {
      // Subsequent runs: send only new or updated calls
      const updates = [];

      for (const [callId, call] of currentCalls.entries()) {
        const prev = cachedCalls.get(callId);

        if (!prev) {
          updates.push({ type: "NEW", call });
        } else if (
          call.last_updated_time > prev.last_updated_time ||
          call.status !== prev.status ||
          call.display_status !== prev.display_status
        ) {
          updates.push({ type: "UPDATE", call });
        }
      }

      for (const item of updates) {
        await sendTelegramMessage(formatTelegramMessage(item.call));
        sentCount++;
      }

      cachedCalls = currentCalls;
    }

    return res.status(200).json({
      success: true,
      timestamp: new Date().toISOString(),
      totalCalls: currentCalls.size,
      sentUpdates: sentCount,
    });
  } catch (error) {
    console.error("Vercel cron handler error:", error);
    return res.status(500).json({
      success: false,
      error: error.message,
    });
  }
}
