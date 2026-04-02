# PycrashAI - Product Requirements Document
## AI-Powered Crash Reconstruction Platform

**Version:** 1.0 | **Date:** 2026-04-01 | **Status:** Draft

---

## 1. EMPATHIZE - Understanding the User

### 1.1 Primary Personas

**"Mike" - The Solo Reconstructionist**
- Former highway patrol officer, now private consultant
- ACTAR-certified, 15 years experience
- Runs a 2-person firm, handles 40-60 cases/year
- Currently pays $5,000-8,000/year for PC-Crash license
- Spends 60% of his time on report writing, not analysis
- Pain: "I spend more time formatting Word documents than doing physics"
- Income: $5,000-$10,000 per engagement

**"Sarah" - The Litigation Attorney**
- Personal injury attorney at a mid-size firm
- Orders 8-12 crash reconstructions per year
- Needs results in 2-4 weeks, often gets them in 6-8
- Doesn't understand the physics but needs to cross-examine opposing experts
- Pain: "I can't tell if my expert's work is actually good until trial"
- Spends: $5,000-$15,000 per reconstruction

**"Dave" - The Insurance SIU Analyst**
- Works at a major insurer's Special Investigations Unit
- Reviews 200+ claims/year, orders reconstruction on ~30
- Needs fast turnaround for fraud detection
- Pain: "By the time I get a reconstruction report, we've already settled"
- Budget: $3,000-$5,000 per case, wants it under $1,000

**"Dr. Chen" - The Academic Researcher**
- University professor in mechanical engineering
- Publishes SAE papers on crash dynamics
- Needs reproducible, transparent simulation tools
- Pain: "Commercial tools are black boxes I can't cite in papers"
- Budget: Grant-funded, needs open source

### 1.2 Jobs To Be Done

| Job | Current Solution | Time | Cost |
|-----|-----------------|------|------|
| Extract crash parameters from police report | Manual reading + spreadsheet | 2-4 hours | $300-600 |
| Look up vehicle specs (weight, wheelbase, stiffness) | NHTSA database + manufacturer specs | 1-2 hours | $150-300 |
| Set up and run simulation | PC-Crash / HVE | 4-8 hours | $600-1,200 |
| Run sensitivity analysis | Manual reruns (if done at all) | 4-8 hours | $600-1,200 |
| Write expert report | Word template + manual | 8-16 hours | $1,200-2,400 |
| Create demonstrative exhibits | PowerPoint + manual | 4-8 hours | $600-1,200 |
| **Total per engagement** | | **23-46 hours** | **$3,450-$6,900** |

### 1.3 Key Insight

> **80% of crash reconstructions are straightforward rear-end or intersection collisions that follow the exact same workflow every time.** The physics is settled. The methodology is published. The only reason they cost $5,000-$15,000 is the manual labor of a credentialed human clicking through software and writing reports.

---

## 2. DEFINE - The Problem

### 2.1 Problem Statement

Crash reconstruction is a $500M-$1B/year US market dominated by $5,000-$8,000/year closed-source software and $150-$300/hour expert labor. The workflow from police report to expert report is manual, repetitive, and slow. No tool exists that can:

1. **Ingest** a police report and automatically extract crash parameters
2. **Configure** a physics simulation from those parameters
3. **Run** the simulation with uncertainty quantification
4. **Generate** a court-admissible expert report

...in minutes instead of weeks.

### 2.2 Value Proposition

**For reconstructionists:** 10x throughput. Handle 400 cases/year instead of 40. No more $8K/year software licenses. Run it on your laptop for free.

**For attorneys:** Same-day preliminary results instead of 6-week wait. Integrated sensitivity analysis that shows "even if speed was 5 mph different, the conclusion holds."

**For researchers:** Open-source, reproducible, citable. Every simulation is a JSON config that anyone can re-run. Publish papers with code that reviewers can actually execute.

**For the community:** Free, open, GPLv3. Anyone can contribute vehicle data, validation tests, report templates, or new physics models. No vendor lock-in, no subscription walls.

### 2.3 Daubert Defensibility (Non-Negotiable)

Every output must satisfy Daubert/Frye admissibility criteria:
- **Testable:** All algorithms are open-source and reproducible
- **Peer-reviewed:** Based on published SAE papers (Carpenter & Welcher, Steffan, etc.)
- **Known error rate:** Monte Carlo sensitivity analysis quantifies uncertainty
- **Standards:** Follows ACTAR and SAE J2868 methodology
- **Generally accepted:** Uses the same physics as PC-Crash and HVE

**Critical rule:** The AI generates narrative. It never generates numbers. Every numerical claim traces to simulation output or input data.

---

## 3. IDEATE - The Solution

### 3.1 Product: PycrashAI

An AI-powered crash reconstruction platform that runs locally via Docker. Four integrated components:

```
+------------------------------------------------------------------+
|                        PycrashAI Platform                         |
|                                                                   |
|  +------------------+    +-------------------+                    |
|  |  Extraction      |    |  Simulation       |                    |
|  |  Agent           |--->|  Engine           |                    |
|  |                  |    |  (pycrash core)   |                    |
|  |  Police report   |    |                   |                    |
|  |  -> structured   |    |  SDOF / IMPC /    |                    |
|  |     params       |    |  Sideswipe        |                    |
|  +------------------+    +--------+----------+                    |
|                                   |                               |
|  +------------------+    +--------v----------+                    |
|  |  Report          |    |  Monte Carlo      |                    |
|  |  Generator       |<---|  Engine           |                    |
|  |                  |    |                   |                    |
|  |  PDF / DOCX /    |    |  N=10,000 runs   |                    |
|  |  HTML reports    |    |  sensitivity      |                    |
|  |  with exhibits   |    |  distributions    |                    |
|  +------------------+    +-------------------+                    |
|                                                                   |
|  +----------------------------------------------------------+    |
|  |  Web Interface (React) + API (FastAPI)                    |    |
|  |  Chat-based interaction, drag-drop positioning,           |    |
|  |  real-time simulation progress, report preview            |    |
|  +----------------------------------------------------------+    |
+------------------------------------------------------------------+
|  Docker Compose: api + worker + redis + frontend                  |
+------------------------------------------------------------------+
```

### 3.2 Component Breakdown

#### Component 1: Extraction Agent
**Input:** Police crash report (PDF/text), witness statements, photos
**Output:** Structured JSON matching pycrash Vehicle input dicts

How it works:
- Claude API with tool_use extracts: vehicles (year/make/model/weight), speeds, angles, positions, road conditions, skid marks
- Vehicle database lookup enriches with physical specs (weight, wheelbase, stiffness)
- Validation layer checks physical plausibility (e.g., speed > 0, weight > 1000 lb)
- Human-in-the-loop confirmation before simulation runs

Claude tools defined:
- `extract_vehicle` -> `{year, make, model, weight, wb, lcgf, lcgr, ...}`
- `extract_crash_conditions` -> `{impact_speed, impact_angle, cor, road_friction, ...}`
- `extract_scene_data` -> `{skid_marks, point_of_rest, road_grade, ...}`
- `lookup_vehicle_specs` -> queries NHTSA/internal database

#### Component 2: Simulation Engine
**Input:** Structured vehicle dicts + crash parameters
**Output:** `vehicle.model` DataFrame with full time-series

This is pycrash core, wrapped in a FastAPI endpoint:
- Model selection logic: SDOF for simple energy analysis, IMPC for full momentum, Sideswipe for glancing impacts
- Configurable timestep, friction, stiffness parameters
- Returns: delta-V, peak acceleration, crush depth, vehicle paths, energy balance

#### Component 3: Monte Carlo Engine
**Input:** Base simulation config + uncertainty ranges
**Output:** Probability distributions of key outputs

- Vary: speed (+/-5 mph), friction (+/-0.1), stiffness (+/-20%), angle (+/-5 deg)
- Run N=1,000-10,000 simulations via Celery workers
- Output: histograms of delta-V, P(injury), confidence intervals
- Key metric: "Even at 95% confidence, delta-V exceeds X mph"

#### Component 4: Report Generator
**Input:** Simulation results + Monte Carlo distributions + case metadata
**Output:** PDF expert report with exhibits

Report sections:
1. Case Summary (AI-generated narrative from inputs)
2. Vehicle Data (tables from input dicts)
3. Methodology (templated, references SAE papers)
4. Simulation Parameters (tables from config)
5. Results (tables + plots from simulation output)
6. Sensitivity Analysis (Monte Carlo distributions)
7. Conclusions (AI-generated, grounded in numerical results)
8. Appendix: Full simulation data, reproducibility instructions

Generation pipeline:
```
Simulation DataFrame + MC results
    -> Plotly figures exported as PNG
    -> Claude generates narrative sections (grounded in data)
    -> Jinja2 HTML template assembly
    -> WeasyPrint -> PDF
```

**THE RULE:** Claude writes prose connecting numbers. It never invents numbers. Every figure in the report has a `source: simulation_output.column[row]` trace.

---

## 4. PROTOTYPE - Architecture

### 4.1 Docker-Compose Stack

```yaml
services:
  api:        # FastAPI backend - simulation endpoints, agent orchestration
  worker:     # Celery worker - runs simulations + Monte Carlo
  redis:      # Message broker + result cache
  frontend:   # React app (or served static build)
```

**One command to run:** `docker compose up`
**One command to test:** `docker compose run api pytest`

### 4.2 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend** | FastAPI + Pydantic | Type-safe API, async, OpenAPI auto-docs |
| **Task Queue** | Celery + Redis | Distributed MC simulation, progress tracking |
| **AI Agent** | Anthropic SDK (direct) | Claude tool_use for extraction + narration |
| **Simulation** | pycrash (this repo) | The physics engine |
| **Report Gen** | Jinja2 + WeasyPrint | HTML templates -> PDF |
| **Frontend** | React + Plotly.js | Interactive viz, chat interface |
| **Deployment** | Docker Compose | Local-first, no cloud dependency |
| **Database** | SQLite (local) | Case persistence, vehicle database |

### 4.3 API Design

```
POST /api/v1/extract
  Body: { text: "police report content...", files: [...] }
  Response: { vehicles: [...], crash_params: {...}, confidence: {...} }

POST /api/v1/simulate
  Body: { vehicles: [...], model: "sdof|impc|sideswipe", params: {...} }
  Response: { job_id: "...", status: "queued" }

GET /api/v1/simulate/{job_id}
  Response: { status: "running|complete", progress: 0.75, results: {...} }

WS /api/v1/simulate/{job_id}/stream
  Streams: progress updates, intermediate results

POST /api/v1/montecarlo
  Body: { base_config: {...}, variations: {...}, n_runs: 10000 }
  Response: { job_id: "..." }

GET /api/v1/montecarlo/{job_id}
  Response: { status: "...", distributions: {...}, confidence_intervals: {...} }

POST /api/v1/report
  Body: { simulation_id: "...", montecarlo_id: "...", case_info: {...} }
  Response: { report_url: "/reports/case_123.pdf" }

GET /api/v1/vehicles/lookup?year=2020&make=Toyota&model=Camry
  Response: { weight: 3400, wb: 9.17, lcgf: 4.3, ... }
```

### 4.4 Data Flow

```
Police Report PDF
    |
    v
[Extraction Agent] -- Claude API tool_use
    |
    +-> Vehicle 1 dict (validated)
    +-> Vehicle 2 dict (validated)
    +-> Crash parameters (validated)
    |
    v
[Human Review] -- User confirms/adjusts extracted params
    |
    v
[Simulation Engine] -- pycrash SDOF/IMPC/Sideswipe
    |
    +-> vehicle.model DataFrame (time-series)
    +-> delta-V, peak accel, crush, energy
    |
    v
[Monte Carlo Engine] -- Celery workers, N=10,000
    |
    +-> delta-V distribution
    +-> confidence intervals
    +-> sensitivity rankings
    |
    v
[Report Generator] -- Claude narrative + Jinja2 + WeasyPrint
    |
    +-> PDF expert report
    +-> HTML interactive version
    +-> JSON reproducibility package
```

### 4.5 Project Structure

```
pycrash/
  ... (existing package)

pycrash_ai/
  docker-compose.yml          # One command: docker compose up
  Dockerfile.api              # FastAPI + pycrash
  Dockerfile.worker           # Celery + pycrash
  Dockerfile.frontend         # React build

  api/
    __init__.py
    main.py                   # FastAPI app
    routes/
      extract.py              # Police report extraction
      simulate.py             # Simulation endpoints
      montecarlo.py           # MC analysis endpoints
      report.py               # Report generation
      vehicles.py             # Vehicle database lookup
    agent/
      extraction_agent.py     # Claude-powered parameter extraction
      report_agent.py         # Claude-powered narrative generation
      tools.py                # Tool definitions for Claude API
    tasks/
      simulation_tasks.py     # Celery tasks for simulation
      montecarlo_tasks.py     # Celery tasks for MC runs
      report_tasks.py         # Celery tasks for PDF generation
    templates/
      report_base.html        # Jinja2 report template
      report.css              # Report styling
    db/
      vehicle_database.py     # SQLite vehicle specs lookup
      vehicles.json           # Seed data (common vehicles)
    config.py                 # Settings (API keys, defaults)

  frontend/                   # React app (Phase 2)
    src/
      App.tsx
      components/
        ChatInterface.tsx     # AI chat for reconstruction
        SimulationView.tsx    # Results visualization
        VehicleEditor.tsx     # Edit extracted parameters
        ReportPreview.tsx     # Preview generated report

  tests/
    test_extraction.py        # Agent extraction tests
    test_simulation_api.py    # API endpoint tests
    test_montecarlo.py        # MC distribution tests
    test_report.py            # Report generation tests
```

---

## 5. TEST - Validation Strategy

### 5.1 Physics Validation
- All existing 137 pycrash tests must pass
- SDOF results validated against SAE published data
- IMPC results validated against Carpenter & Welcher
- Monte Carlo distributions validated: mean should match deterministic run

### 5.2 Extraction Validation
- Test corpus: 50 real police report templates with known ground truth
- Extraction accuracy target: >90% on vehicle make/model/year, >80% on speed estimates
- False positive rate: <5% (extracted values that are wrong and pass validation)

### 5.3 Report Validation
- Every number in generated report must trace to simulation output
- No hallucinated values (automated check: compare report numbers to source data)
- Report format validated by practicing reconstructionist review

### 5.4 Daubert Validation
- Methodology section references specific SAE paper numbers
- Monte Carlo provides quantified error rates
- Full reproducibility: report includes JSON config that recreates the simulation
- Open-source code satisfies transparency requirement

---

## 6. IMPLEMENT - Phased Roadmap

### Phase 1: Foundation (This Sprint)
**Goal:** `docker compose up` gives you a working API that runs crash simulations

- FastAPI backend wrapping pycrash
- Celery + Redis for async simulation jobs
- SDOF and single-vehicle simulation endpoints
- Vehicle database (top 100 US vehicles by sales)
- Docker Compose with hot-reload for development
- Full test suite for API endpoints
- **Deliverable:** Run a crash simulation via curl

### Phase 2: Intelligence (Next Sprint)
**Goal:** Paste a police report, get a simulation

- Claude-powered extraction agent
- Police report PDF parsing
- Human-in-the-loop parameter confirmation API
- Monte Carlo engine with Celery distribution
- Basic report generation (HTML + PDF)
- **Deliverable:** Police report -> PDF report pipeline

### Phase 3: Interface (Sprint 3)
**Goal:** Web UI that non-technical users can operate

- React frontend with chat-based interaction
- Drag-drop vehicle positioning on scene diagram
- Real-time simulation progress via WebSocket
- Interactive Plotly result visualization
- Report preview and download
- **Deliverable:** Full web app for crash reconstruction

### Phase 4: Scale (Sprint 4)
**Goal:** Production-ready platform

- User authentication and case management
- Vehicle database expansion (NHTSA full catalog)
- EDR data import support
- Photo-based crush measurement (CV)
- Multi-language report generation
- API rate limiting and usage tracking
- **Deliverable:** Self-hosted platform anyone can run locally

---

## 7. METRICS - Success Criteria

| Metric | Current State | Phase 1 Target | Phase 2 Target |
|--------|--------------|-----------------|----------------|
| Time: report to simulation | 4-8 hours | 5 minutes (API) | 30 seconds (auto) |
| Time: simulation to report | 8-16 hours | N/A | 10 minutes |
| Cost per reconstruction | $3,450-$6,900 | $0 (your hardware) | $0.10 (AI API call) |
| Simulation accuracy | Same as pycrash | Same as pycrash | Same + uncertainty |
| Cases per reconstructionist/year | 40-60 | 200+ | 400+ |
| Daubert challenges survived | N/A | Same as manual | Better (MC + transparency) |

---

## 8. RISKS AND MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI extracts wrong speed from report | Incorrect simulation | Human-in-the-loop confirmation required before simulation |
| Report contains hallucinated numbers | Daubert challenge, malpractice | Automated trace-back check: every number must map to data source |
| Opposing expert challenges AI-generated report | Case loss | Report explicitly states AI-assisted; methodology is identical to manual |
| Claude API downtime | Can't extract/generate | Extraction falls back to manual input; simulation runs independently |
| Over-reliance on automation | Expert de-skilling | Tool augments, not replaces. Expert must review and sign off |
| LLM API costs for extraction/narration | Recurring expense | Optional — all core simulation works without any API key. BYO key model. |

---

## 9. COMPETITIVE POSITIONING

```
                    High Automation
                         |
                         |  PycrashAI
                         |  (AI + open source + self-hosted)
                         |
    Open Source ----------+---------- Proprietary
                         |
                PC-Crash  |  Virtual CRASH
                HVE       |
                         |
                    Low Automation
```

**PycrashAI is the only solution in the upper-left quadrant.** Open source AND AI-powered. Every competitor is proprietary and manual.

### Why This Wins
1. **GPLv3 open source** — no license fees, ever. Community-owned.
2. **Daubert-proof transparency** — opposing experts can read every line of code. Try that with PC-Crash.
3. **AI-powered workflow** is 10-50x faster than manual reconstruction
4. **Monte Carlo built-in** provides uncertainty quantification that most tools lack
5. **Docker self-hosted** — your data never leaves your machine. No cloud dependency.
6. **Python ecosystem** — infinite extensibility. Any researcher can contribute.
7. **BYO API key** — AI features work with your own Anthropic/OpenAI key. No middleman.

### Community Growth Strategy
- Publish validation notebooks comparing PycrashAI vs PC-Crash vs HVE on the same crash tests
- Submit SAE paper on open-source crash reconstruction with uncertainty quantification
- Partner with ACTAR for training materials
- University adoption for teaching crash reconstruction
- Reconstructionist community contributions (vehicle database, validation data, report templates)
