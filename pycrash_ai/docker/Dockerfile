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

# Install pycrash core
COPY README.md setup.py pyproject.toml ./
COPY pycrash/ pycrash/
RUN pip install --no-cache-dir ".[dev]"

# Install pycrash_ai dependencies (not part of pycrash's extras)
RUN pip install --no-cache-dir \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "celery[redis]>=5.4" \
    "redis>=5.0" \
    "anthropic>=0.39" \
    "openai>=1.30" \
    "weasyprint>=62.0" \
    "jinja2>=3.1" \
    "python-multipart>=0.0.9" \
    "pydantic>=2.0" \
    "PyMuPDF>=1.24" \
    "httpx>=0.27"

# Copy platform code
COPY pycrash_ai/ pycrash_ai/

# Run as non-root user
RUN useradd --create-home appuser \
    && mkdir -p /app/reports \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
