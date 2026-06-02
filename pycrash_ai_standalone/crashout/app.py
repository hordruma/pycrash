"""Crashout - FastAPI application."""
from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os

from crashout.routes import simulate, extract, montecarlo, report, vehicles, pipeline, cases
from crashout.config import settings

logger = logging.getLogger("crashout")

app = FastAPI(
    title="Crashout",
    description="AI-powered crash reconstruction platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Middleware (declared order: auth, rate-limit, logging)
# FastAPI runs middleware in REVERSE declaration order, so logging runs first
# (outermost), then rate-limit, then auth (innermost).
# ---------------------------------------------------------------------------

# Rate limit storage: {ip: [timestamp, ...]}
_rate_limits: dict[str, list[float]] = defaultdict(list)

# Paths that require stricter rate limits
_HEAVY_PREFIXES = ("/api/v1/simulate/", "/api/v1/montecarlo/", "/api/v1/pipeline/")


@app.middleware("http")
async def auth_middleware(request, call_next):
    """Require Bearer token on /api/ routes when PYCRASH_API_KEY is set."""
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    api_key = settings.api_key
    if not api_key:  # No key configured = no auth required
        return await call_next(request)

    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {api_key}":
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"},
        )

    return await call_next(request)


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """Simple in-memory per-IP rate limiting."""
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Determine limit based on path
    is_heavy = any(request.url.path.startswith(p) for p in _HEAVY_PREFIXES)
    limit = 10 if is_heavy else 100
    window = 60  # seconds

    # Build a per-bucket key so heavy and normal limits are tracked separately
    bucket = f"{client_ip}:heavy" if is_heavy else f"{client_ip}:normal"

    # Purge timestamps older than the window
    _rate_limits[bucket] = [t for t in _rate_limits[bucket] if now - t < window]

    if len(_rate_limits[bucket]) >= limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
        )

    _rate_limits[bucket].append(now)
    return await call_next(request)


@app.middleware("http")
async def log_middleware(request, call_next):
    """Log method, path, status code, and duration for every request."""
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    logger.info(
        "%s %s %s %0.fms",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response

# Mount routes
app.include_router(simulate.router, prefix="/api/v1", tags=["simulation"])
app.include_router(extract.router, prefix="/api/v1", tags=["extraction"])
app.include_router(montecarlo.router, prefix="/api/v1", tags=["montecarlo"])
app.include_router(report.router, prefix="/api/v1", tags=["report"])
app.include_router(vehicles.router, prefix="/api/v1", tags=["vehicles"])
app.include_router(pipeline.router, prefix="/api/v1", tags=["pipeline"])
app.include_router(cases.router, prefix="/api/v1", tags=["cases"])

# Serve generated reports
os.makedirs(settings.reports_dir, exist_ok=True)
app.mount("/reports", StaticFiles(directory=settings.reports_dir), name="reports")


@app.get("/")
def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


@app.get("/health")
def health():
    return {"status": "healthy"}


# Mount static files AFTER all API routes to avoid catching all requests
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
