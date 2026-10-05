# How to Run (Python)

1. Create a `.env` file from `.env.example`:
```env
BOT_TOKEN="your_telegram_bot_token"
CHAT_ID="your_telegram_chat_id"
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run:
```bash
python bot.py
```

4. (Optional) Run 24/7 in background with PM2:
```bash
pm2 start bot.py --name "hdfc-py" --interpreter python
```
