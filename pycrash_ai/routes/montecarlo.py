"""Monte Carlo analysis API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pycrash_ai.models import MonteCarloRequest, MonteCarloStatus

router = APIRouter()


@router.post("/montecarlo", response_model=MonteCarloStatus)
def start_montecarlo(req: MonteCarloRequest):
    """Queue a Monte Carlo analysis (requires Celery + Redis)."""
    try:
        from pycrash_ai.tasks.simulation_tasks import run_montecarlo
        task = run_montecarlo.delay(
            base_params=req.base_config.model_dump(),
            variations=[v.model_dump() for v in req.variations],
            n_runs=req.n_runs,
        )
        return MonteCarloStatus(
            job_id=task.id, status="queued",
            total_runs=req.n_runs,
        )
    except ImportError:
        raise HTTPException(503, "Monte Carlo requires Celery + Redis. Run via Docker.")


@router.get("/montecarlo/{job_id}", response_model=MonteCarloStatus)
def get_montecarlo_status(job_id: str):
    """Check Monte Carlo job status (requires Celery + Redis)."""
    try:
        from celery.result import AsyncResult
    except ImportError:
        raise HTTPException(503, "Job status requires Celery. Run via Docker.")

    result = AsyncResult(job_id)

    if result.state == "PENDING":
        return MonteCarloStatus(job_id=job_id, status="queued", total_runs=0)
    elif result.state == "RUNNING":
        meta = result.info or {}
        return MonteCarloStatus(
            job_id=job_id, status="running",
            progress=meta.get("progress", 0),
            completed_runs=meta.get("completed", 0),
            total_runs=meta.get("total", 0),
        )
    elif result.state == "SUCCESS":
        return MonteCarloStatus(
            job_id=job_id, status="complete",
            progress=1.0,
            completed_runs=result.result.get("completed_runs", 0),
            total_runs=result.result.get("total_runs", 0),
            results=result.result,
        )
    elif result.state == "FAILURE":
        return MonteCarloStatus(job_id=job_id, status="failed", total_runs=0)
    else:
        return MonteCarloStatus(job_id=job_id, status=result.state, total_runs=0)
