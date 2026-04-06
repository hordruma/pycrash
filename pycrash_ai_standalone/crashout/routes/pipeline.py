"""Full reconstruction pipeline - police report in, results out.

The pipeline:
1. Extract crash data from text (AI or heuristic)
2. Store extraction results in the case graph (evidence space)
3. Look up vehicle specs from database and add to graph
4. Detect contradictions and gaps
5. Project evidence to pycrash simulation parameters
6. Run SDOF simulation
7. Return everything including graph state
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from crashout.agent.extraction_agent import extract_from_text, _sanitize_input
from crashout.models import ExtractionResponse
from crashout.graph.store import get_store

router = APIRouter()


class PipelineRequest(BaseModel):
    """Full pipeline request: text in, reconstruction out."""
    text: str = Field(..., min_length=10, description="Police report or crash description")
    auto_simulate: bool = Field(True, description="Run simulation automatically after extraction")
    cor: float = Field(0.15, ge=0, le=1, description="Coefficient of restitution")
    tstop: float = Field(0.5, gt=0, le=5, description="Simulation stop time (s)")


class PipelineResponse(BaseModel):
    """Full pipeline results."""
    extraction: ExtractionResponse
    vehicle_specs: Optional[List[Dict[str, Any]]] = None
    simulation: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    case_id: Optional[str] = None
    graph: Optional[Dict[str, Any]] = None


@router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(
    req: PipelineRequest,
    x_provider: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    x_model: Optional[str] = Header(None),
):
    """Full crash reconstruction pipeline.

    1. Extract crash data from text (AI or heuristic)
    2. Look up vehicle specs from database
    3. Run SDOF simulation
    4. Return everything

    This is the end-to-end pipeline: paste a police report, get a reconstruction.
    """
    # Step 1: Sanitize and extract
    sanitized_text = _sanitize_input(req.text)
    extraction = await extract_from_text(
        text=sanitized_text,
        provider_name=x_provider,
        api_key=x_api_key,
        model=x_model,
    )

    # Step 2: Build case graph from extraction
    store = get_store()
    case_id = f"pipeline_{uuid.uuid4().hex[:8]}"
    case = store.create_case(case_id=case_id, title="Pipeline auto-case")
    case.add_scene()

    source_id = case.add_source(
        source_type="police_report",
        description="Pipeline text input",
    )

    # Add vehicles to graph
    for i, veh in enumerate(extraction.vehicles, 1):
        case.add_vehicle(
            vehicle_number=i,
            make=veh.make,
            model=veh.model,
            year=veh.year,
            role=veh.role or "unknown",
        )
        # Add extracted evidence
        if veh.estimated_speed_mph is not None:
            case.add_evidence(
                category="speed", key="estimated_speed_mph",
                value=veh.estimated_speed_mph, unit="mph",
                confidence=0.7, source_type="police_report",
                source_id=source_id, applies_to_vehicle=i,
            )
        if veh.travel_direction:
            case.add_evidence(
                category="heading", key="travel_direction",
                value=veh.travel_direction, unit="",
                confidence=0.8, source_type="police_report",
                source_id=source_id, applies_to_vehicle=i,
            )
        if veh.damage_description:
            case.add_evidence(
                category="damage", key="damage_description",
                value=veh.damage_description, unit="",
                confidence=0.8, source_type="police_report",
                source_id=source_id, applies_to_vehicle=i,
            )

    # Add scene evidence
    if extraction.scene:
        if extraction.scene.road_surface:
            case.add_evidence(
                category="road_surface", key="surface",
                value=extraction.scene.road_surface, unit="",
                confidence=0.9, source_type="police_report",
                source_id=source_id, applies_to_scene=True,
            )
        if extraction.scene.weather:
            case.add_evidence(
                category="weather", key="weather",
                value=extraction.scene.weather, unit="",
                confidence=0.9, source_type="police_report",
                source_id=source_id, applies_to_scene=True,
            )

    # Step 3: Look up vehicle specs and add to graph
    vehicle_specs = []
    for i, veh in enumerate(extraction.vehicles, 1):
        spec = _lookup_vehicle(veh.year, veh.make, veh.model)
        if spec:
            # Add database specs as evidence
            for key in ("weight", "wb", "lcgf", "lcgr", "width", "length",
                        "hcg", "track", "izz", "A", "B", "k"):
                if key in spec:
                    case.add_evidence(
                        category="vehicle_spec", key=key,
                        value=spec[key], unit="lb" if key == "weight" else "ft",
                        confidence=0.95, source_type="database",
                        applies_to_vehicle=i,
                    )
            for key in ("fwd", "rwd", "awd"):
                if key in spec:
                    case.add_evidence(
                        category="vehicle_spec", key=key,
                        value=spec[key], unit="",
                        confidence=0.95, source_type="database",
                        applies_to_vehicle=i,
                    )

            # Override speed from extraction
            if veh.estimated_speed_mph is not None:
                spec["vx_initial"] = veh.estimated_speed_mph * 1.46667
            if veh.role == "striking":
                spec["striking"] = True
            vehicle_specs.append(spec)

    # Step 4: Simulate (if we have enough data)
    simulation = None
    if req.auto_simulate and len(vehicle_specs) >= 2:
        simulation = _run_sdof(vehicle_specs[0], vehicle_specs[1], req.cor, req.tstop)

    # Step 5: Summary
    summary = None
    if simulation:
        summary = (
            f"SDOF Analysis: Vehicle 1 delta-V = {simulation['delta_v1_mph']} mph, "
            f"Vehicle 2 delta-V = {simulation['delta_v2_mph']} mph. "
            f"Peak crush = {simulation['peak_crush_ft']} ft, "
            f"impact duration = {simulation['impact_duration_ms']} ms."
        )

    # Export graph state
    graph_export = case.export()

    return PipelineResponse(
        extraction=extraction,
        vehicle_specs=vehicle_specs,
        simulation=simulation,
        summary=summary,
        case_id=case_id,
        graph=graph_export,
    )


def _lookup_vehicle(year: Optional[int], make: Optional[str],
                    model: Optional[str]) -> Optional[Dict[str, Any]]:
    """Look up vehicle from database, return pycrash-compatible dict."""
    import os

    db_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "vehicles.json"
    )
    if not os.path.exists(db_path):
        return _default_vehicle(make, model)

    with open(db_path) as f:
        vehicles = json.load(f)

    # Try exact match
    for v in vehicles:
        if (make and v.get("make", "").lower() == make.lower() and
                model and v.get("model", "").lower() == model.lower()):
            result = v.copy()
            result["year"] = year or v.get("year")
            return result

    # Try make-only match
    if make:
        for v in vehicles:
            if v.get("make", "").lower() == make.lower():
                result = v.copy()
                result["year"] = year or v.get("year")
                result["model"] = model or v.get("model")
                return result

    return _default_vehicle(make, model)


def _default_vehicle(make: Optional[str] = None,
                     model: Optional[str] = None) -> Dict[str, Any]:
    """Return a generic mid-size sedan when no database match."""
    return {
        "year": 2020, "make": make or "Unknown", "model": model or "Sedan",
        "weight": 3400, "wb": 9.17, "lcgf": 4.4, "lcgr": 4.77,
        "width": 6.0, "length": 16.0, "hcg": 1.8, "track": 5.17,
        "f_hang": 3.2, "r_hang": 3.7, "tire_d": 2.2, "tire_w": 0.7,
        "izz": 2500, "fwd": 1, "rwd": 0, "awd": 0,
        "A": 300, "B": 150, "k": 50000, "L": 60, "c": 12,
        "vx_initial": 0, "vy_initial": 0, "omega_z": 0,
        "init_x_pos": 0, "init_y_pos": 0, "head_angle": 0,
        "brake": 0, "steer_ratio": 16, "striking": False,
        "vin": "", "source": "default_estimate",
    }


def _run_sdof(veh1_spec: Dict[str, Any], veh2_spec: Dict[str, Any],
              cor: float, tstop: float) -> Dict[str, Any]:
    """Run SDOF simulation from vehicle specs."""
    from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel

    w1 = veh1_spec["weight"]
    w2 = veh2_spec["weight"]
    v1_fps = veh1_spec.get("vx_initial", 0)
    v2_fps = veh2_spec.get("vx_initial", 0)
    v1_mph = v1_fps / 1.46667
    v2_mph = v2_fps / 1.46667
    k = min(veh1_spec.get("k", 50000), veh2_spec.get("k", 50000))

    result_df = SingleDOFmodel(
        W1=w1, v1_initial=v1_mph, v1_brake=0,
        W2=w2, v2_initial=v2_mph, v2_brake=0,
        k=k, cor=cor, tstop=tstop,
        ktype="constantK", ttype=1,
    )

    m1, m2 = w1 / 32.2, w2 / 32.2
    v1_init = v1_mph * 1.46667
    v2_init = v2_mph * 1.46667
    v1_final = float(result_df.v1.iloc[-1])
    v2_final = float(result_df.v2.iloc[-1])

    # Impact duration
    contact_mask = result_df.springF > 0
    if contact_mask.any():
        contact_times = result_df.t[contact_mask]
        impact_duration = float(contact_times.iloc[-1] - contact_times.iloc[0])
    else:
        impact_duration = 0.0

    return {
        "model": "sdof",
        "delta_v1_mph": round(abs(v1_final - v1_init) * 0.681818, 2),
        "delta_v2_mph": round(abs(v2_final - v2_init) * 0.681818, 2),
        "delta_v1_fps": round(abs(v1_final - v1_init), 2),
        "delta_v2_fps": round(abs(v2_final - v2_init), 2),
        "v1_final_fps": round(v1_final, 2),
        "v2_final_fps": round(v2_final, 2),
        "peak_crush_ft": round(abs(float(result_df.dx.min())), 4),
        "peak_force_lb": round(float(result_df.springF.max()), 1),
        "peak_accel_v1_g": round(float(result_df.a1.abs().max()) / 32.2, 2),
        "peak_accel_v2_g": round(float(result_df.a2.abs().max()) / 32.2, 2),
        "impact_duration_ms": round(impact_duration * 1000, 1),
        "inputs": {
            "w1": w1, "w2": w2,
            "v1_mph": round(v1_mph, 1), "v2_mph": round(v2_mph, 1),
            "k": k, "cor": cor,
        },
    }
