# HDFC Sky Research Recommendation Telegram Monitor (Python)

A real-time 24/7 Python background monitor for HDFC Sky research recommendations and trading calls, broadcasting live market alerts to Telegram with rich formatting, expandable dropdowns, bold keys, and monospace values.

---

## 1. Local Setup

1. Open `python/.env` (or copy from `python/.env.example`):
```env
BOT_TOKEN="your_telegram_bot_token"
CHAT_ID="your_telegram_chat_id"

# Optional: Real-time Live API (from browser inspect)
HDFCSKY_AUTH_TOKEN="your_x_authorization_token"
HDFCSKY_DEVICE_ID="your_device_id"
```

2. Install dependencies:
```bash
cd python
pip install -r requirements.txt
```

3. (Optional) Generate Auth Token via Phone + OTP + Password:
If `HDFCSKY_AUTH_TOKEN` is not set, you can run the interactive authentication wizard:
```bash
python auth.py
```
This validates your phone number, sends an OTP, verifies your password/PIN, and automatically saves the token to `python/.env`.

4. Run the bot:
```bash
python bot.py
```
*(If no token is found when starting `bot.py` interactively, it will automatically offer to generate one for you).*

---

## 2. Deploy to Railway (24/7 Cloud Background Service)

1. Go to [railway.app](https://railway.app) and create a **New Project**.
2. Select **Deploy from GitHub repo** and choose this repository.
3. In **Variables**, add:
   - `BOT_TOKEN`: `your_telegram_bot_token`
   - `CHAT_ID`: `your_telegram_chat_id`
   - `HDFCSKY_AUTH_TOKEN`: `your_token` (optional)
   - `HDFCSKY_DEVICE_ID`: `your_device_id` (optional)
4. Railway will automatically detect the `Procfile` / `Dockerfile` and start the Python monitor daemon 24/7.

---

## 3. Run with Docker

```bash
docker build -t hdfcsky-monitor .
docker run -d --name hdfcsky-monitor \
  --env BOT_TOKEN="your_bot_token" \
  --env CHAT_ID="your_chat_id" \
  hdfcsky-monitor
```

---

## 4. Run 24/7 in Background on VPS (PM2)

```bash
cd python
pm2 start bot.py --name "hdfcsky-bot" --interpreter python
pm2 save
pm2 startup
```
