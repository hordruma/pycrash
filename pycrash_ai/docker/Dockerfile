FROM python:3.11-slim

WORKDIR /app

# System deps for WeasyPrint PDF generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip + build tools
RUN pip install --no-cache-dir --upgrade pip "setuptools>=68.0,<82" wheel

# Install pycrash core + all extras
COPY README.md setup.py pyproject.toml ./
COPY pycrash/ pycrash/
RUN pip install --no-cache-dir ".[dev,ai]"

# Copy platform code
COPY pycrash_ai/ pycrash_ai/

# Run as non-root user
RUN useradd --create-home appuser \
    && mkdir -p /app/reports \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
