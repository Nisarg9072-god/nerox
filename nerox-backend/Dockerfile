FROM python:3.11-slim

# ── Python env optimisations ──────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Avoids pip caching inside the image layer (~100 MB saving)
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only PyTorch first (explicit index prevents accidental CUDA pull),
# then the rest of the dependencies.
RUN pip install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --no-cache-dir \
    -r requirements.txt

# Playwright browsers (needed for dynamic web ingestion in auto-detect)
# `--with-deps` installs required OS packages and downloads Chromium.
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
