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


@router.post("/montecarlo/sync")
def run_montecarlo_sync(req: MonteCarloRequest):
    """Run Monte Carlo analysis synchronously (no Redis/Celery needed)."""
    import numpy as np
    from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel

    n_runs = min(req.n_runs, 5000)
    base_params = req.base_config.model_dump()
    variations = [v.model_dump() for v in req.variations]

    rng = np.random.default_rng()
    results_dv1 = []
    results_dv2 = []
    results_crush = []

    for i in range(n_runs):
        # Apply variations
        params = base_params.copy()
        for var in variations:
            param_name = var["parameter"]
            if param_name not in params:
                continue
            if var["distribution"] == "uniform":
                params[param_name] = rng.uniform(var["min_value"], var["max_value"])
            elif var["distribution"] == "normal":
                mean = (var["min_value"] + var["max_value"]) / 2
                std = (var["max_value"] - var["min_value"]) / 4
                params[param_name] = rng.normal(mean, std)
            elif var["distribution"] == "triangular":
                mid = (var["min_value"] + var["max_value"]) / 2
                params[param_name] = rng.triangular(var["min_value"], mid, var["max_value"])

        try:
            result_df = SingleDOFmodel(
                W1=params["w1"],
                v1_initial=params["v1"],
                v1_brake=params.get("v1_brake", 0),
                W2=params["w2"],
                v2_initial=params["v2"],
                v2_brake=params.get("v2_brake", 0),
                k=params["k"],
                cor=params["cor"],
                tstop=params["tstop"],
                ktype="constantK",
                ttype=1,
            )

            v1_init_fps = params["v1"] * 1.46667
            v2_init_fps = params["v2"] * 1.46667
            dv1 = abs(float(result_df.v1.iloc[-1]) - v1_init_fps) * 0.681818
            dv2 = abs(float(result_df.v2.iloc[-1]) - v2_init_fps) * 0.681818
            crush = abs(float(result_df.dx.min()))

            results_dv1.append(dv1)
            results_dv2.append(dv2)
            results_crush.append(crush)
        except Exception:
            continue  # Skip failed runs

    if not results_dv1:
        raise HTTPException(500, "All Monte Carlo runs failed.")

    dv1_arr = np.array(results_dv1)
    dv2_arr = np.array(results_dv2)
    crush_arr = np.array(results_crush)

    def stats(arr: np.ndarray):
        return {
            "mean": round(float(arr.mean()), 2),
            "std": round(float(arr.std()), 2),
            "min": round(float(arr.min()), 2),
            "max": round(float(arr.max()), 2),
            "p5": round(float(np.percentile(arr, 5)), 2),
            "p25": round(float(np.percentile(arr, 25)), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p75": round(float(np.percentile(arr, 75)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "values": arr.round(2).tolist(),
        }

    return {
        "completed_runs": len(results_dv1),
        "total_runs": n_runs,
        "delta_v1_mph": stats(dv1_arr),
        "delta_v2_mph": stats(dv2_arr),
        "peak_crush_ft": stats(crush_arr),
    }


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
