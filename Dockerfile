# Use official Python image
FROM python:3.11-slim

WORKDIR /app

# Upgrade pip to latest
RUN pip install --upgrade pip setuptools wheel

# Copy requirements first (for Docker caching)
COPY requirements.txt .

# --- FIX ---
# Install httpx[http2]==0.24.1 first to ensure h2/hpack/hyperframe are present
RUN pip install --no-cache-dir "httpx[http2]==0.24.1"

# Then install everything else
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full app
COPY . .

# Expose port for Render
EXPOSE 8000

# Start the Gunicorn server
CMD ["gunicorn", "-k", "gevent", "-w", "1", "-b", "0.0.0.0:8000", "app:app"]



