# CLAUDE.md - Crashout Development Guide

## What This Is

Crashout is an AI-powered vehicle crash reconstruction web platform built on top of the [pycrash](https://pypi.org/project/pycrash/) physics engine. It provides a web UI, REST API, LLM-powered report extraction, and case management for accident reconstruction professionals and non-technical users.

**License:** GPLv3 | **Python:** >=3.9 | **Version:** 0.1.0

## Repository Layout

```
crashout/                     # Main package
  app.py                        # FastAPI application entry point
  config.py                     # App-wide configuration (env vars, defaults)
  models.py                     # Pydantic request/response models

  agent/                        # LLM-powered extraction
    extraction_agent.py         # Multi-provider crash report extraction
    ingest.py                   # Dual-path document ingestion (text + vision)
    llm_provider.py             # Anthropic/OpenAI provider abstraction
    tools.py                    # LLM tool definitions

  graph/                        # 6-layer crash reconstruction hypergraph
    schema.py                   # Node labels, edge types, layer definitions
    store.py                    # CaseGraphStore with disk persistence
    layers/                     # Mixin classes, one per graph layer
      entity.py                 # Vehicles, drivers, objects
      temporal.py               # Events, phases, timeline
      spatial.py                # Positions, trajectories, impact points
      evidence.py               # Evidence, sources, contradictions, gaps
      causal.py                 # Contributing factors, causal chains
      physical.py               # Delta-V, forces, crush, energy

  routes/                       # FastAPI route handlers
    cases.py                    # Case hypergraph CRUD + cross-layer queries
    extract.py                  # AI extraction from text/PDF/image
    pipeline.py                 # End-to-end: report in, reconstruction out
    simulate.py                 # SDOF, IMPC, sideswipe simulation endpoints
    montecarlo.py               # Monte Carlo uncertainty analysis (sync + async)
    report.py                   # PDF/HTML report generation
    vehicles.py                 # Vehicle database lookup

  tasks/                        # Celery async task workers
    worker.py                   # Celery app configuration
    simulation_tasks.py         # Async SDOF and Monte Carlo tasks

  static/                       # Web UI (no build step)
    index.html                  # SPA shell with Alpine.js router
    css/app.css                 # Custom styles
    js/                         # Alpine.js page components
    pages/                      # HTML page partials loaded dynamically

  data/
    vehicles.json               # Vehicle specs database (50+ vehicles)

  docker/
    Dockerfile
    docker-compose.yml

tests/                          # pytest test suite
  test_api.py
```

## Architecture

### Core Dependency

This platform imports `pycrash` (the physics engine) as an external PyPI dependency. The only import used is:
```python
from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel
```
This appears in 3 files: `routes/simulate.py`, `routes/pipeline.py`, `tasks/simulation_tasks.py`. All imports are lazy (inside functions).

### API Structure

All API endpoints are under `/api/v1/`:
- `/api/v1/simulate/` - SDOF, IMPC, sideswipe simulations
- `/api/v1/montecarlo/` - Monte Carlo uncertainty analysis
- `/api/v1/pipeline/` - End-to-end reconstruction from text
- `/api/v1/extract/` - AI extraction from text/PDF/image
- `/api/v1/cases/` - 6-layer hypergraph case management
- `/api/v1/vehicles/` - Vehicle database lookup
- `/api/v1/report/` - PDF/HTML report generation

### Web UI

Single-page app served from FastAPI static files:
- Alpine.js 3.x for reactivity (CDN)
- Tailwind CSS (CDN)
- Plotly.js for charts (CDN)
- Pages loaded dynamically as HTML partials via fetch + Alpine.initTree()

### Security

- Optional API key auth via `PYCRASH_API_KEY` env var
- Rate limiting: 100 req/min general, 10 req/min for simulation endpoints
- LLM input sanitization against prompt injection
- Non-root Docker container user

## Build & Run

```bash
# Docker (recommended)
cd docker
cp ../.env.example .env  # Add your API keys
docker compose up --build
# Open http://localhost:8100

# Without Docker
pip install -e ".[dev]"
uvicorn crashout.app:app --reload --port 8100
# Note: Monte Carlo async and Reports require Celery + Redis (use Docker)
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Via Docker
docker compose run api pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYCRASH_API_KEY` | (none) | API key for auth (optional, no auth if unset) |
| `ANTHROPIC_API_KEY` | (none) | For AI extraction with Claude |
| `OPENAI_API_KEY` | (none) | For AI extraction with GPT |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for Celery |
| `FALKORDB_URL` | `redis://localhost:6379/0` | FalkorDB graph DB |
| `PYCRASH_CASES_DIR` | `./data/cases` | Disk persistence for cases |
| `PYCRASH_ENV` | `development` | Environment name |

## Key Design Decisions

- **pycrash as external dep**: Imported via `pip install pycrash`, not embedded. Clean separation between physics engine and web platform.
- **All units imperial**: lb, ft, ft/s, degrees. Matches pycrash conventions.
- **No build step for UI**: Alpine.js + Tailwind CDN. Zero Node.js tooling.
- **Sync + async paths**: SDOF and Monte Carlo have both sync (no Celery) and async (Celery) endpoints so the platform works with or without Docker.
- **6-layer hypergraph**: Cases organize crash data across entity, temporal, spatial, evidence, causal, and physical layers with cross-layer traversals.
