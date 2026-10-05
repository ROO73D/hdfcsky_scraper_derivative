# How to Run (Node.js)

1. Create a `.env` file from `.env.example`:
```env
BOT_TOKEN="your_telegram_bot_token"
CHAT_ID="your_telegram_chat_id"
```

2. Run:
```bash
npm start
```

3. (Optional) Run 24/7 in background with PM2:
```bash
pm2 start bot.js --name "hdfc-js"
```
