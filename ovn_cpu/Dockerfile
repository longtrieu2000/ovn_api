FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    OVN_CPU_HOST=0.0.0.0 \
    OVN_CPU_PORT=8002

# Install system dependencies
RUN apt-get update && apt-get install -y \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose metrics port
EXPOSE 8002

# Run the FastAPI CPU monitor service from /app/app.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host ${OVN_CPU_HOST} --port ${OVN_CPU_PORT}"]
