# PycrashAI - Getting Started

AI-powered crash reconstruction. Paste a police report, get a full simulation.

## What You Need

- **Docker Desktop** - [Download here](https://www.docker.com/products/docker-desktop/)
  - Windows/Mac: install and make sure it's running (whale icon in your taskbar)
  - Linux: install Docker Engine + Docker Compose
- **An API key** (optional, for AI features):
  - [Anthropic (Claude)](https://console.anthropic.com/) or [OpenAI (GPT)](https://platform.openai.com/)
  - Without a key everything still works, just uses basic text matching instead of AI

## Quick Start (5 minutes)

### 1. Get the code

```bash
git clone https://github.com/hordruma/pycrash.git
cd pycrash
```

### 2. Set up your API key (optional)

Create a file called `.env` in the `pycrash_ai/` folder:

```bash
# On Mac/Linux:
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > pycrash_ai/.env

# Or for OpenAI:
echo "OPENAI_API_KEY=sk-your-key-here" > pycrash_ai/.env
```

Or skip this step entirely -- the system works without AI, just with simpler text extraction.

### 3. Start everything

```bash
cd pycrash_ai
docker compose up --build
```

First time takes 2-3 minutes (downloading images, installing packages).
You'll see logs scrolling -- wait until you see:

```
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Open the API

Open your browser to: **http://localhost:8000/docs**

You'll see the interactive API documentation where you can try everything out.

## Try It Out

### Run a crash simulation (no API key needed)

Click **POST /api/v1/simulate/sdof/sync** in the docs page, click "Try it out", paste this:

```json
{
  "w1": 3400,
  "w2": 2900,
  "v1": 30,
  "v2": 0,
  "cor": 0.15,
  "k": 50000,
  "tstop": 0.5
}
```

Click **Execute**. You'll get back delta-V, peak force, crush depth, and more.

What this means:
- `w1`/`w2`: vehicle weights in pounds (3,400 lb Camry hits a 2,900 lb Civic)
- `v1`/`v2`: speeds in mph (30 mph into a stopped car)
- `cor`: coefficient of restitution (0.15 = mostly plastic collision)
- `k`: combined stiffness in lb/ft
- `tstop`: simulation duration in seconds

### Extract crash data from a police report

Click **POST /api/v1/extract**, click "Try it out", paste:

```json
{
  "text": "On 03/15/2024, Vehicle 1, a 2020 Toyota Camry driven by John Smith, was traveling northbound on Main Street at approximately 35 mph. Vehicle 2, a 2019 Honda Civic driven by Jane Doe, was stopped at the red light at the intersection of Main Street and Oak Avenue. Vehicle 1 failed to stop and struck Vehicle 2 in the rear. Both vehicles sustained moderate damage. Road was dry asphalt, weather was clear."
}
```

The system extracts vehicles, speeds, roles (striking/struck), and scene conditions automatically.

### Full pipeline: report in, reconstruction out

Click **POST /api/v1/pipeline**, paste:

```json
{
  "text": "Vehicle 1, a 2020 Toyota Camry traveling at approximately 35 mph, struck Vehicle 2, a 2019 Honda Civic, which was stopped at a red light. Dry road, clear weather.",
  "auto_simulate": true,
  "cor": 0.15
}
```

This runs the full chain: extract crash data, look up vehicle specs, run SDOF simulation, build a case graph, return everything.

### Create a case (evidence hypergraph)

Build up a case piece by piece:

```bash
# Create a case
curl -X POST http://localhost:8000/api/v1/cases \
  -H "Content-Type: application/json" \
  -d '{"case_id": "case-001", "title": "Main St rear-end collision"}'

# Add vehicles
curl -X POST http://localhost:8000/api/v1/cases/case-001/vehicles \
  -H "Content-Type: application/json" \
  -d '{"vehicle_number": 1, "make": "Toyota", "model": "Camry", "year": 2020, "role": "striking"}'

curl -X POST http://localhost:8000/api/v1/cases/case-001/vehicles \
  -H "Content-Type: application/json" \
  -d '{"vehicle_number": 2, "make": "Honda", "model": "Civic", "year": 2019, "role": "struck"}'

# Add evidence
curl -X POST http://localhost:8000/api/v1/cases/case-001/evidence \
  -H "Content-Type: application/json" \
  -d '{"category": "speed", "key": "estimated_speed_mph", "value": 35, "unit": "mph", "confidence": 0.7, "source_type": "witness", "applies_to_vehicle": 1}'

# Check what's missing
curl http://localhost:8000/api/v1/cases/case-001/gaps

# Export the case
curl http://localhost:8000/api/v1/cases/case-001/export
```

### Look up vehicle specs

```bash
# Search by make
curl "http://localhost:8000/api/v1/vehicles/lookup?make=Toyota"

# Search by make and model
curl "http://localhost:8000/api/v1/vehicles/lookup?make=Toyota&model=Camry"

# List all available makes
curl http://localhost:8000/api/v1/vehicles/makes
```

## What's Running

Docker starts 4 services:

| Service | What it does | Port |
|---------|-------------|------|
| **api** | FastAPI web server - handles all requests | 8000 |
| **worker** | Celery worker - runs async simulations | (internal) |
| **redis** | Message queue for async jobs | 6379 |
| **falkordb** | Graph database for case evidence | 6380 |

## Stopping

```bash
# Press Ctrl+C in the terminal, or:
docker compose down

# To also remove stored data:
docker compose down -v
```

## Running Without Docker (simpler but limited)

If you just want to try the simulation endpoints without Docker:

```bash
cd pycrash
pip install -e .
pip install fastapi uvicorn python-multipart pydantic

# Start the server
uvicorn pycrash_ai.api.main:app --host 0.0.0.0 --port 8000 --reload
```

This gives you the sync simulation, extraction, vehicle lookup, and case graph endpoints.
Async simulation (`/simulate/sdof`) and Monte Carlo require the full Docker setup.

## API Endpoints Reference

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/v1/simulate/sdof/sync` | POST | Run SDOF crash simulation |
| `/api/v1/extract` | POST | Extract crash data from text |
| `/api/v1/extract/upload` | POST | Extract from PDF/image upload |
| `/api/v1/pipeline` | POST | Full pipeline: text in, reconstruction out |
| `/api/v1/cases` | POST/GET | Create/list crash cases |
| `/api/v1/cases/{id}` | GET | Case overview with gaps and contradictions |
| `/api/v1/cases/{id}/vehicles` | POST/GET | Add/list vehicles |
| `/api/v1/cases/{id}/drivers` | POST/GET | Add/list drivers |
| `/api/v1/cases/{id}/evidence` | POST | Add evidence |
| `/api/v1/cases/{id}/events` | POST | Add timeline events |
| `/api/v1/cases/{id}/factors` | POST/GET | Add/list contributing factors |
| `/api/v1/cases/{id}/delta-v` | POST | Add delta-V results |
| `/api/v1/cases/{id}/crush` | POST | Add crush data |
| `/api/v1/cases/{id}/impact-points` | POST/GET | Add/list impact points |
| `/api/v1/cases/{id}/gaps` | GET | Find missing simulation parameters |
| `/api/v1/cases/{id}/contradictions` | GET | Find conflicting evidence |
| `/api/v1/cases/{id}/project` | GET | Project evidence to pycrash inputs |
| `/api/v1/cases/{id}/timeline` | GET | Get event timeline |
| `/api/v1/cases/{id}/timeline/full` | GET | Full timeline with all layers |
| `/api/v1/cases/{id}/causal-chain` | GET | Get contributing factor chain |
| `/api/v1/cases/{id}/layers` | GET | Hypergraph layer summary |
| `/api/v1/cases/{id}/export` | GET | Export case as .crash file |
| `/api/v1/cases/import` | POST | Import a .crash file |
| `/api/v1/vehicles/lookup` | GET | Look up vehicle specs |
| `/api/v1/vehicles/makes` | GET | List available vehicle makes |
| `/api/v1/report` | POST | Generate PDF/HTML report |
| `/docs` | GET | Interactive API documentation |

## Troubleshooting

**"Docker is not running"** -- Open Docker Desktop and wait for it to fully start.

**Port 8000 already in use** -- Something else is using that port. Either stop it or change the port in `docker-compose.yml` (change `"8000:8000"` to `"9000:8000"`, then use `http://localhost:9000`).

**Build fails** -- Make sure you're in the `pycrash_ai/` directory, not the root. Run `docker compose up --build` (not `docker-compose`, note the space).

**"Cannot connect to the Docker daemon"** -- Docker Desktop needs to be running. On Linux, you may need `sudo`.

**API key not working** -- Make sure your `.env` file is in the `pycrash_ai/` folder (not the root), and the key format is correct (`ANTHROPIC_API_KEY=sk-ant-...` or `OPENAI_API_KEY=sk-...`).
