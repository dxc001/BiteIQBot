FROM python:3.11-bullseye

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update && apt-get install -y git build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# install base stack first
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
        Flask \
        APScheduler \
        gunicorn \
        gevent \
        stripe \
        openai \
        python-dotenv \
        python-telegram-bot==20.7 \
        httpx==0.27.0 && \
    # now force-install supabase without pulling its conflicting deps
    pip install --no-deps git+https://github.com/supabase-community/supabase-py.git@v2.3.0 && \
    pip freeze > requirements.lock

COPY . .
EXPOSE 8000
CMD ["gunicorn", "-k", "gevent", "-w", "1", "-b", "0.0.0.0:8000", "app:app"]


