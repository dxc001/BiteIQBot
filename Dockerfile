FROM python:3.11-bullseye

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y git build-essential && rm -rf /var/lib/apt/lists/*

# install base python deps
COPY requirements.txt .

# allow pip to resolve freely and cache its solution
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir "python-telegram-bot>=20.6,<21" \
                                "supabase>=1.0,<2.0" \
                                stripe openai Flask APScheduler gunicorn gevent python-dotenv && \
    pip freeze > requirements.lock

COPY . .

EXPOSE 8000
CMD ["gunicorn", "-k", "gevent", "-w", "1", "-b", "0.0.0.0:8000", "app:app"]

