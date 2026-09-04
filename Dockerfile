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
    LLM_MODEL=gemini-3.8-flash \
    GEMINI_THINKING_LEVEL=LOW \
    # Default skip for small cloud hosts (512MB). Override to 0 for full RAG warmup.
    F1_SKIP_WARMUP=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU torch first (no CUDA nvidia-* packages), then the rest of requirements.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
      "torch==2.2.2+cpu" \
    && pip install --no-cache-dir -r requirements.txt

COPY app.py server.py pdf_processor.py historical_processor.py \
     setup_historical_data.py setup_driver_numbers.py ./
COPY utils ./utils
COPY data ./data
# Indexes + historical CSVs are committed for cloud builds.
COPY vector_store ./vector_store
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/api/health')" || exit 1

CMD ["sh", "-c", "uvicorn server:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]
