FROM python:3.11-slim

WORKDIR /app

RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .

# Force httpx[http2] install first
RUN pip install --no-cache-dir "httpx[http2]==0.24.1"

# Then install everything else
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "gunicorn -k gevent -w 1 -b 0.0.0.0:${PORT:-8080} app:app"]



