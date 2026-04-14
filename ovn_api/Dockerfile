FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    APP_MODULE=app.main:app \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8001 \
    UVICORN_EXTRA_ARGS=

RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    gcc \
    python3-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8001

CMD ["sh", "-c", "exec python -m uvicorn ${APP_MODULE} --host ${UVICORN_HOST} --port ${UVICORN_PORT} ${UVICORN_EXTRA_ARGS}"]
