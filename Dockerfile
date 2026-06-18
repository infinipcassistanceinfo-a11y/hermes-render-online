FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

# Set work directory
WORKDIR /app

# Install basic system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# --- PLAYWRIGHT & BROWSER-USE OPTIONAL CONFIGURATION ---
# If you want to enable a headless browser in the future, uncomment the block below:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
#     libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
#     libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
#     && rm -rf /var/lib/apt/lists/*
# RUN pip install playwright && playwright install --with-deps chromium
# -------------------------------------------------------

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose port
EXPOSE $PORT

# Start application using Gunicorn
CMD gunicorn --bind 0.0.0.0:$PORT main:app
