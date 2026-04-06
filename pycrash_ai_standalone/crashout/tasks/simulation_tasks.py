"""Celery tasks for crash simulation."""
from __future__ import annotations

import json
from typing import Any, Dict

from crashout.tasks.worker import app


@app.task(bind=True, name="run_sdof_simulation")
def run_sdof_simulation(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Run an SDOF crash simulation as a Celery task."""
    self.update_state(state="RUNNING", meta={"progress": 0.1})

    from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel

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

    self.update_state(state="RUNNING", meta={"progress": 0.8})

    # Extract key results
    m1 = params["w1"] / 32.2
    m2 = params["w2"] / 32.2

    v1_initial_fps = params["v1"] * 1.46667
    v2_initial_fps = params["v2"] * 1.46667
    v1_final = float(result_df.v1.iloc[-1])
    v2_final = float(result_df.v2.iloc[-1])

    dv1_fps = abs(v1_final - v1_initial_fps)
    dv2_fps = abs(v2_final - v2_initial_fps)
    dv1_mph = dv1_fps * 0.681818
    dv2_mph = dv2_fps * 0.681818

    peak_crush = float(result_df.dx.min())
    peak_force = float(result_df.springF.max())
    peak_a1 = float(result_df.a1.abs().max())
    peak_a2 = float(result_df.a2.abs().max())

    # Impact duration (time spring force > 0)
    contact_mask = result_df.springF > 0
    if contact_mask.any():
        contact_times = result_df.t[contact_mask]
        impact_duration = float(contact_times.iloc[-1] - contact_times.iloc[0])
    else:
        impact_duration = 0.0

    results = {
        "delta_v1_mph": round(dv1_mph, 2),
        "delta_v2_mph": round(dv2_mph, 2),
        "delta_v1_fps": round(dv1_fps, 2),
        "delta_v2_fps": round(dv2_fps, 2),
        "v1_final_fps": round(v1_final, 2),
        "v2_final_fps": round(v2_final, 2),
        "peak_crush_ft": round(abs(peak_crush), 4),
        "peak_force_lb": round(peak_force, 1),
        "peak_accel_v1_g": round(peak_a1 / 32.2, 2),
        "peak_accel_v2_g": round(peak_a2 / 32.2, 2),
        "impact_duration_ms": round(impact_duration * 1000, 1),
        "momentum_initial": round(m1 * v1_initial_fps + m2 * v2_initial_fps, 2),
        "momentum_final": round(m1 * v1_final + m2 * v2_final, 2),
        "model_data": {
            "t": result_df.t.round(4).tolist(),
            "x1": result_df.x1.round(4).tolist(),
            "x2": result_df.x2.round(4).tolist(),
            "v1": result_df.v1.round(4).tolist(),
            "v2": result_df.v2.round(4).tolist(),
            "a1": result_df.a1.round(2).tolist(),
            "a2": result_df.a2.round(2).tolist(),
            "springF": result_df.springF.round(2).tolist(),
            "dx": result_df.dx.round(6).tolist(),
        },
    }

    self.update_state(state="RUNNING", meta={"progress": 1.0})
    return results


@app.task(bind=True, name="run_montecarlo")
def run_montecarlo(self, base_params: Dict[str, Any],
                   variations: list, n_runs: int) -> Dict[str, Any]:
    """Run Monte Carlo analysis as a Celery task."""
    import numpy as np
    from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel

    rng = np.random.default_rng()
    results_dv1 = []
    results_dv2 = []
    results_crush = []

    for i in range(n_runs):
        if i % 100 == 0:
            self.update_state(
                state="RUNNING",
                meta={"progress": i / n_runs, "completed": i, "total": n_runs},
            )

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

    dv1_arr = np.array(results_dv1)
    dv2_arr = np.array(results_dv2)
    crush_arr = np.array(results_crush)

    def stats(arr: np.ndarray) -> Dict[str, float]:
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
