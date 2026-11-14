FROM python:3.12-slim-bookworm

# Metadata
LABEL maintainer="Sunset Group Lead Scraping & AI Validation System"
LABEL description="Intelligent Dual-Mode Scraping, Bangladesh Phone Normalization, and Groq AI Validation Platform"

# Prevent interactive prompts and configure environment
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001

WORKDIR /app

# Install system dependencies required for Patchright / Playwright Headless Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    git \
    build-essential \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications first for optimal Docker layer caching
COPY requirements.txt pyproject.toml setup.cfg* ./

# Upgrade pip and install Python requirements
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Install local scrapling library in editable mode
RUN pip install --no-cache-dir -e .

# Install Chromium browser binaries and dependencies for patchright & playwright
RUN python -m patchright install-deps chromium || true && \
    python -m patchright install chromium && \
    python -m playwright install chromium

# Create data directory for SQLite persistence
RUN mkdir -p /app/data

# Expose application port
EXPOSE 8001

# Container health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

# Launch the FastAPI application using uvicorn on port 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
