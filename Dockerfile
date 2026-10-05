FROM node:20-alpine

WORKDIR /app

# Copy project files
COPY package.json ./
COPY js/ ./js/

# Set production environment
ENV NODE_ENV=production

# Start 24/7 background monitor
CMD ["node", "js/bot.js"]
