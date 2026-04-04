"""Simulation API routes."""
from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException

from pycrash_ai.models import SDOFRequest, SimulationStatus, VisualizationRequest

router = APIRouter()


@router.post("/simulate/sdof", response_model=SimulationStatus)
def start_sdof_simulation(req: SDOFRequest):
    """Queue an SDOF crash simulation (requires Celery + Redis)."""
    try:
        from pycrash_ai.tasks.simulation_tasks import run_sdof_simulation
        task = run_sdof_simulation.delay(req.model_dump())
        return SimulationStatus(job_id=task.id, status="queued")
    except ImportError:
        raise HTTPException(503, "Async simulation requires Celery + Redis. Use /simulate/sdof/sync instead or run via Docker.")


@router.post("/simulate/sdof/sync")
def run_sdof_sync(req: SDOFRequest):
    """Run SDOF simulation synchronously (no Redis/Celery needed)."""
    from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel

    result_df = SingleDOFmodel(
        W1=req.w1, v1_initial=req.v1, v1_brake=req.v1_brake,
        W2=req.w2, v2_initial=req.v2, v2_brake=req.v2_brake,
        k=req.k, cor=req.cor, tstop=req.tstop,
        ktype="constantK", ttype=1,
    )

    m1, m2 = req.w1 / 32.2, req.w2 / 32.2
    v1_init = req.v1 * 1.46667
    v2_init = req.v2 * 1.46667
    v1_final = float(result_df.v1.iloc[-1])
    v2_final = float(result_df.v2.iloc[-1])

    return {
        "status": "complete",
        "delta_v1_mph": round(abs(v1_final - v1_init) * 0.681818, 2),
        "delta_v2_mph": round(abs(v2_final - v2_init) * 0.681818, 2),
        "peak_crush_ft": round(abs(float(result_df.dx.min())), 4),
        "peak_force_lb": round(float(result_df.springF.max()), 1),
        "peak_accel_v1_g": round(float(result_df.a1.abs().max()) / 32.2, 2),
        "peak_accel_v2_g": round(float(result_df.a2.abs().max()) / 32.2, 2),
        "v1_final_fps": round(v1_final, 2),
        "v2_final_fps": round(v2_final, 2),
        "momentum_conserved": round(
            abs((m1 * v1_final + m2 * v2_final) - (m1 * v1_init + m2 * v2_init)), 4
        ),
    }


@router.get("/simulate/{job_id}", response_model=SimulationStatus)
def get_simulation_status(job_id: str):
    """Check simulation job status (requires Celery + Redis)."""
    try:
        from celery.result import AsyncResult
    except ImportError:
        raise HTTPException(503, "Job status requires Celery. Run via Docker.")

    result = AsyncResult(job_id)

    if result.state == "PENDING":
        return SimulationStatus(job_id=job_id, status="queued")
    elif result.state == "RUNNING":
        meta = result.info or {}
        return SimulationStatus(
            job_id=job_id, status="running",
            progress=meta.get("progress", 0),
        )
    elif result.state == "SUCCESS":
        return SimulationStatus(
            job_id=job_id, status="complete",
            progress=1.0, results=result.result,
        )
    elif result.state == "FAILURE":
        return SimulationStatus(
            job_id=job_id, status="failed",
            error=str(result.info),
        )
    else:
        return SimulationStatus(job_id=job_id, status=result.state)


def _vehicle_corners(x: float, y: float, length: float, width: float, heading_deg: float) -> list[tuple[float, float]]:
    """Compute the four corners of a rotated vehicle rectangle."""
    h = math.radians(heading_deg)
    cos_h, sin_h = math.cos(h), math.sin(h)
    hw, hl = width / 2, length / 2
    corners = [
        (x + hl * cos_h - hw * sin_h, y + hl * sin_h + hw * cos_h),  # front-left
        (x + hl * cos_h + hw * sin_h, y + hl * sin_h - hw * cos_h),  # front-right
        (x - hl * cos_h + hw * sin_h, y - hl * sin_h - hw * cos_h),  # rear-right
        (x - hl * cos_h - hw * sin_h, y - hl * sin_h + hw * cos_h),  # rear-left
    ]
    return corners


@router.post("/simulate/visualize")
def generate_crash_visualization(req: VisualizationRequest):
    """Generate a 2D crash scene diagram as Plotly JSON."""
    traces = []

    for veh in req.vehicles:
        corners = _vehicle_corners(veh.x, veh.y, veh.length, veh.width, veh.heading)
        # Close the polygon by repeating the first corner
        xs = [c[0] for c in corners] + [corners[0][0]]
        ys = [c[1] for c in corners] + [corners[0][1]]

        # Filled vehicle polygon
        traces.append({
            "type": "scatter",
            "x": xs,
            "y": ys,
            "mode": "lines",
            "fill": "toself",
            "fillcolor": veh.color,
            "opacity": 0.4,
            "line": {"color": veh.color, "width": 2},
            "name": veh.label,
            "showlegend": True,
        })

        # Vehicle label at center
        traces.append({
            "type": "scatter",
            "x": [veh.x],
            "y": [veh.y],
            "mode": "text",
            "text": [veh.label],
            "textposition": "middle center",
            "textfont": {"size": 11, "color": "black"},
            "showlegend": False,
        })

    # Impact point marker
    if req.impact_point and "x" in req.impact_point and "y" in req.impact_point:
        traces.append({
            "type": "scatter",
            "x": [req.impact_point["x"]],
            "y": [req.impact_point["y"]],
            "mode": "markers+text",
            "marker": {"symbol": "x", "size": 14, "color": "red", "line": {"width": 2}},
            "text": ["Impact"],
            "textposition": "top center",
            "textfont": {"size": 10, "color": "red"},
            "name": "Impact Point",
            "showlegend": True,
        })

    layout = {
        "title": {"text": req.title},
        "xaxis": {
            "title": "X (ft)",
            "scaleanchor": "y",
            "scaleratio": 1,
            "showgrid": req.show_grid,
            "gridcolor": "#e5e7eb",
            "zeroline": True,
        },
        "yaxis": {
            "title": "Y (ft)",
            "showgrid": req.show_grid,
            "gridcolor": "#e5e7eb",
            "zeroline": True,
        },
        "showlegend": True,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Inter, system-ui, sans-serif", "size": 12},
        "margin": {"t": 50, "r": 20, "b": 50, "l": 60},
    }

    fig_dict = {"data": traces, "layout": layout}
    return {"plotly_json": fig_dict}
