# How to Run & Deploy

## 1. Local Setup

Create a `.env` file in the folder you want to use (`python/` or `js/`) with your Telegram credentials:

```env
BOT_TOKEN="your_telegram_bot_token"
CHAT_ID="your_telegram_chat_id"
```

### Run Python:
```bash
cd python
pip install -r requirements.txt
python bot.py
```

### Run Node.js:
```bash
cd js
npm start
```

---

## 2. Deploy to Railway (24/7 1-Second Monitoring)

1. Go to [railway.app](https://railway.app) and create a **New Project**.
2. Select **Deploy from GitHub repo** and choose this repository.
3. In **Variables**, add:
   - `BOT_TOKEN`: `your_telegram_bot_token`
   - `CHAT_ID`: `your_telegram_chat_id`
4. Railway will automatically detect the `Procfile` / `Dockerfile` and start the monitor daemon 24/7.

---

## 3. Deploy to Vercel (Automated Cron)

1. Go to [vercel.com](https://vercel.com) and import this repository.
2. In **Environment Variables**, add:
   - `BOT_TOKEN`: `your_telegram_bot_token`
   - `CHAT_ID`: `your_telegram_chat_id`
3. Click **Deploy**.
4. Vercel automatically runs the cron job (`/api/cron`) every minute in the background.

---

## 4. Run 24/7 in Background on VPS (PM2)

### Python:
```bash
cd python
pm2 start bot.py --name "hdfc-monitor" --interpreter python
```

### Node.js:
```bash
cd js
pm2 start bot.js --name "hdfc-monitor"
```
