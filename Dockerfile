# Use official Python image
FROM python:3.11-slim

WORKDIR /app

# Upgrade pip first to support extras syntax
RUN pip install --upgrade pip setuptools wheel

# Copy requirements
COPY requirements.txt .

# --- CRITICAL FIX ---
# Force install httpx[http2] FIRST so h2, hpack, hyperframe are in place
RUN pip install --no-cache-dir "httpx[http2]==0.27.0"

# Then install all other dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code
COPY . .

# Expose port for Render
EXPOSE 8000

# Start Gunicorn
CMD ["gunicorn", "-k", "gevent", "-w", "1", "-b", "0.0.0.0:8000", "app:app"]



