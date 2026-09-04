# syntax=docker/dockerfile:1

# --- Frontend build ---
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Python runtime ---
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    LLM_PROVIDER=gemini \
    LLM_MODEL=gemini-2.0-flash \
    F1_SKIP_WARMUP=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py server.py pdf_processor.py historical_processor.py \
     setup_historical_data.py setup_driver_numbers.py ./
COPY utils ./utils
COPY data ./data
# Build with local indexes present (gitignored). Create empty dirs if missing.
COPY vector_store ./vector_store
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/api/health')" || exit 1

CMD ["sh", "-c", "uvicorn server:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]
