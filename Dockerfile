FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY python/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY python/ ./python/

# Start 24/7 background monitor
CMD ["python", "python/bot.py"]
