# PycrashAI - AI-Powered Crash Reconstruction

Upload a police crash report, and PycrashAI uses AI to extract the vehicle and scene data, runs a physics-based crash simulation, and presents the results in a web interface. No engineering background required -- just paste a report and get answers like speed change (delta-V), peak force, and crush depth.

## Features

- **Web interface** for uploading reports and viewing results
- **AI extraction** from police reports, PDFs, and images (supports Anthropic Claude and OpenAI GPT)
- **SDOF crash simulation** powered by the [pycrash](https://pypi.org/project/pycrash/) physics engine
- **Monte Carlo uncertainty analysis** to account for unknowns in input data
- **6-layer hypergraph** for organizing case evidence, timelines, and causal factors
- **PDF and HTML report generation**
- **Built-in vehicle database** with specs for 20 common US vehicles

## Quick Start with Docker (recommended)

This is the easiest way to get everything running.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### Steps

```bash
git clone https://github.com/hordruma/pycrash-ai.git
cd pycrash-ai
```

Optionally, create a `.env` file in the `docker/` folder with your API key:

```bash
# For Anthropic Claude:
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > docker/.env

# Or for OpenAI GPT:
echo "OPENAI_API_KEY=sk-your-key-here" > docker/.env
```

Start everything:

```bash
cd docker
docker compose up --build
```

First run takes 2-3 minutes. When you see `Uvicorn running on http://0.0.0.0:8000`, open your browser to:

**http://localhost:8100**

To stop, press `Ctrl+C` in the terminal, or run `docker compose down`.

> **Note:** AI extraction (reading police reports automatically) requires an API key. The crash simulation works without one -- you can enter vehicle data manually.

## Quick Start without Docker (for developers)

```bash
git clone https://github.com/hordruma/pycrash-ai.git
cd pycrash-ai
pip install -e ".[dev]"
uvicorn pycrash_ai.app:app --reload --port 8100
```

Open **http://localhost:8100** in your browser.

> **Note:** Monte Carlo analysis and PDF report generation require Redis and Celery, which are only available through the Docker setup.

## API Documentation

Interactive API docs are available at:

**http://localhost:8100/docs**

You can try out every endpoint directly from your browser -- no extra tools needed.

## Project Structure

```
pycrash_ai/          Main application package
pycrash_ai/routes/   FastAPI endpoints (simulation, extraction, cases, reports)
pycrash_ai/graph/    6-layer hypergraph for case evidence management
pycrash_ai/agent/    LLM-powered extraction from crash reports
pycrash_ai/static/   Web UI files
pycrash_ai/tasks/    Celery workers for async jobs (Monte Carlo, reports)
docker/              Docker Compose configuration
```

## Built On

PycrashAI is built on top of [pycrash](https://pypi.org/project/pycrash/) ([GitHub](https://github.com/hordruma/pycrash)), a 2D vehicle crash simulation library used in forensic accident reconstruction. The physics engine handles tire models, vehicle dynamics, and three collision models (SDOF, impulse-momentum, and sideswipe).

## License

GPL-3.0
