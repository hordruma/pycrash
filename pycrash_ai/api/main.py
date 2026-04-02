"""PycrashAI - FastAPI application."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from pycrash_ai.api.routes import simulate, extract, montecarlo, report, vehicles, pipeline, cases
from pycrash_ai.api.config import settings

app = FastAPI(
    title="PycrashAI",
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
    return {
        "name": "PycrashAI",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
