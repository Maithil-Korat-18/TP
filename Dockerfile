FROM python:3.13-slim

# Avoid buffering output so logs appear in real-time
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies if needed (e.g. ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Mount volumes for persistent database and logs
VOLUME ["/app/logs", "/app/sih_monitor.db"]

CMD ["python", "app.py"]
