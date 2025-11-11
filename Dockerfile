# ===============================
# BiteIQBot — Stable Render Build
# ===============================

FROM python:3.11-bullseye

# Prevent Python from writing .pyc files & buffering logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y git build-essential && rm -rf /var/lib/apt/lists/*

# Copy dependencies list
COPY requirements.txt .

# Install all Python dependencies with fallback resolver
RUN pip install --upgrade pip setuptools wheel && \
    pip install --use-deprecated=legacy-resolver --no-cache-dir \
        Flask \
        APScheduler \
        gunicorn \
        gevent \
        stripe \
        openai \
        python-dotenv \
        python-telegram-bot==20.7 \
        supabase==2.3.0 \
        httpx && \
    pip freeze > requirements.lock

# Copy your project files
COPY . .

# Expose Flask / Gunicorn port
EXPOSE 8000

# Start the unified Flask + Telegram + Scheduler app
CMD ["gunicorn", "-k", "gevent", "-w", "1", "-b", "0.0.0.0:8000", "app:app"]


