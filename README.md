# How to Run

## 1. Setup Configuration

Create a `.env` file in the folder you want to use (`python/` or `js/`) with your Telegram credentials:

```env
BOT_TOKEN="your_telegram_bot_token"
CHAT_ID="your_telegram_chat_id"
```

---

## 2. Run with Python

```bash
cd python
pip install -r requirements.txt
python bot.py
```

---

## 3. Run with Node.js

```bash
cd js
npm start
```

---

## 4. Run 24/7 in Background (PM2)

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
