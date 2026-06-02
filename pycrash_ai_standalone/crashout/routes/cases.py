"""Case hypergraph API routes — 6-layer evidence space for crash reconstruction.

Manages the FalkorDB/InMemory-backed case hypergraph where:
- Entity layer: vehicles, drivers, objects
- Temporal layer: events, phases, timeline
- Spatial layer: positions, trajectories, impact points
- Evidence layer: evidence, sources, contradictions, gaps
- Causal layer: contributing factors, causal chains
- Physical layer: delta-V, forces, crush, energy

Agents traverse across layers to reason about crash reconstruction.
"""
from __future__ import annotations

import json
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from crashout.config import settings
from crashout.graph.store import get_store

router = APIRouter(prefix="/cases", tags=["cases"])


# ===================================================================
# REQUEST / RESPONSE MODELS
# ===================================================================

class CreateCaseRequest(BaseModel):
    case_id: str = Field(..., min_length=1)
    title: str = Field("")
    date_of_loss: str = Field("")


class AddVehicleRequest(BaseModel):
    vehicle_number: int = Field(..., ge=1)
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    role: str = Field("unknown")


class AddDriverRequest(BaseModel):
    vehicle_number: int = Field(..., ge=1)
    name: Optional[str] = None
    age: Optional[int] = None
    impairment: Optional[str] = None


class AddEvidenceRequest(BaseModel):
    category: str
    key: str
    value: Any
    unit: str = ""
    confidence: float = Field(0.5, ge=0, le=1)
    source_type: str = "analyst"
    source_id: Optional[str] = None
    applies_to_vehicle: Optional[int] = None
    applies_to_scene: bool = False


class AddSourceRequest(BaseModel):
    source_type: str
    description: str = ""


class AddEventRequest(BaseModel):
    event_type: str
    description: str = ""
    t: Optional[float] = None
    phase: Optional[str] = None


class AddPhaseRequest(BaseModel):
    phase_name: str
    t_start: Optional[float] = None
    t_end: Optional[float] = None


class OrderEventsRequest(BaseModel):
    event_id_before: str
    event_id_after: str


class LinkEntityEventRequest(BaseModel):
    entity_id: str
    event_id: str


class AddPositionRequest(BaseModel):
    x: float
    y: float
    heading: float = 0.0
    entity_id: Optional[str] = None
    event_id: Optional[str] = None
    t: Optional[float] = None


class AddImpactPointRequest(BaseModel):
    x: float
    y: float
    vehicle1_number: int
    vehicle2_number: int
    event_id: Optional[str] = None


class AddTrajectoryRequest(BaseModel):
    entity_id: str
    positions: List[Dict[str, float]]  # [{x, y, heading, t}, ...]


class AddFactorRequest(BaseModel):
    factor_type: str
    description: str = ""
    severity: float = Field(0.5, ge=0, le=1)


class LinkFactorRequest(BaseModel):
    factor_id: str
    target_id: str  # event_id, factor_id, or evidence_id
    link_type: str = "caused_by"  # caused_by, contributed_to, supported_by


class AddDeltaVRequest(BaseModel):
    vehicle_number: int
    dvx: float
    dvy: float
    magnitude_mph: Optional[float] = None
    event_id: Optional[str] = None


class AddForceRequest(BaseModel):
    magnitude: float
    direction: float = 0.0
    vehicle_number: Optional[int] = None
    impact_point_id: Optional[str] = None
    event_id: Optional[str] = None


class AddCrushRequest(BaseModel):
    vehicle_number: int
    depth: float
    width: float = 0.0
    profile: Optional[List[float]] = None


class AddEnergyRequest(BaseModel):
    value: float
    unit: str = "ft-lb"
    vehicle_number: Optional[int] = None


class CaseResponse(BaseModel):
    case_id: str
    title: str
    vehicles: List[Dict[str, Any]] = []
    evidence_count: int = 0


# ===================================================================
# STORE SINGLETON
# ===================================================================

_store = None


def _get_store():
    global _store
    if _store is None:
        _store = get_store(cases_dir=settings.cases_dir)
    return _store


def _open_case(case_id: str):
    store = _get_store()
    try:
        return store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")


def _persist_case(case_id: str) -> None:
    """Persist a case to disk after a mutating operation."""
    store = _get_store()
    if hasattr(store, "_persist"):
        store._persist(case_id)


# ===================================================================
# CASE CRUD
# ===================================================================

@router.post("", response_model=CaseResponse)
async def create_case(req: CreateCaseRequest):
    """Create a new crash case hypergraph."""
    store = _get_store()
    case = store.create_case(
        case_id=req.case_id, title=req.title, date_of_loss=req.date_of_loss,
    )
    case.add_scene()
    _persist_case(req.case_id)
    return CaseResponse(case_id=case.case_id, title=case.title)


@router.get("", response_model=List[str])
async def list_cases():
    """List all case IDs."""
    return _get_store().list_cases()


@router.get("/{case_id}")
async def get_case(case_id: str):
    """Get case overview: all layers summarized."""
    case = _open_case(case_id)
    vehicles = case.get_vehicles()
    all_evidence = []
    for veh in vehicles:
        all_evidence.extend(case.get_evidence_for_vehicle(veh["vehicle_number"]))

    return {
        "case_id": case.case_id,
        "title": case.title,
        "vehicles": vehicles,
        "evidence_count": len(all_evidence),
        "gaps": case.find_gaps(),
        "contradictions": case.find_contradictions(),
        "layers": case.get_layer_summary() if hasattr(case, "get_layer_summary") else {},
    }


@router.delete("/{case_id}")
async def delete_case(case_id: str):
    """Delete a case."""
    store = _get_store()
    if hasattr(store, "delete_case"):
        store.delete_case(case_id)
    elif hasattr(store, "_cases"):
        store._cases.pop(case_id, None)
    else:
        raise HTTPException(404, f"Cannot delete case {case_id}")
    return {"deleted": case_id}


# ===================================================================
# ENTITY LAYER
# ===================================================================

@router.post("/{case_id}/vehicles")
async def add_vehicle(case_id: str, req: AddVehicleRequest):
    case = _open_case(case_id)
    vid = case.add_vehicle(
        vehicle_number=req.vehicle_number, make=req.make,
        model=req.model, year=req.year, role=req.role,
    )
    _persist_case(case_id)
    return {"vehicle_id": vid}


@router.get("/{case_id}/vehicles")
async def get_vehicles(case_id: str):
    return _open_case(case_id).get_vehicles()


@router.post("/{case_id}/drivers")
async def add_driver(case_id: str, req: AddDriverRequest):
    case = _open_case(case_id)
    did = case.add_driver(
        vehicle_number=req.vehicle_number, name=req.name,
        age=req.age, impairment=req.impairment,
    )
    _persist_case(case_id)
    return {"driver_id": did}


@router.get("/{case_id}/drivers")
async def get_drivers(case_id: str):
    return _open_case(case_id).get_drivers()


# ===================================================================
# TEMPORAL LAYER
# ===================================================================

@router.post("/{case_id}/events")
async def add_event(case_id: str, req: AddEventRequest):
    case = _open_case(case_id)
    eid = case.add_event(
        event_type=req.event_type, description=req.description,
        t=req.t, phase=req.phase,
    )
    _persist_case(case_id)
    return {"event_id": eid}


@router.post("/{case_id}/phases")
async def add_phase(case_id: str, req: AddPhaseRequest):
    case = _open_case(case_id)
    pid = case.add_phase(
        phase_name=req.phase_name, t_start=req.t_start, t_end=req.t_end,
    )
    _persist_case(case_id)
    return {"phase_id": pid}


@router.post("/{case_id}/events/order")
async def order_events(case_id: str, req: OrderEventsRequest):
    case = _open_case(case_id)
    case.order_events(req.event_id_before, req.event_id_after)
    _persist_case(case_id)
    return {"status": "ordered"}


@router.post("/{case_id}/events/link-entity")
async def link_entity_to_event(case_id: str, req: LinkEntityEventRequest):
    case = _open_case(case_id)
    case.link_entity_to_event(req.entity_id, req.event_id)
    _persist_case(case_id)
    return {"status": "linked"}


@router.get("/{case_id}/timeline")
async def get_timeline(case_id: str):
    return _open_case(case_id).get_timeline()


@router.get("/{case_id}/timeline/full")
async def get_full_timeline(case_id: str):
    """Full timeline with positions, factors, and evidence at each event."""
    return _open_case(case_id).get_full_timeline()


# ===================================================================
# SPATIAL LAYER
# ===================================================================

@router.post("/{case_id}/positions")
async def add_position(case_id: str, req: AddPositionRequest):
    case = _open_case(case_id)
    pid = case.add_position(
        x=req.x, y=req.y, heading=req.heading,
        entity_id=req.entity_id, event_id=req.event_id, t=req.t,
    )
    _persist_case(case_id)
    return {"position_id": pid}


@router.post("/{case_id}/impact-points")
async def add_impact_point(case_id: str, req: AddImpactPointRequest):
    case = _open_case(case_id)
    v1_id = f"{case_id}_v{req.vehicle1_number}"
    v2_id = f"{case_id}_v{req.vehicle2_number}"
    ipid = case.add_impact_point(
        x=req.x, y=req.y, vehicle1_id=v1_id, vehicle2_id=v2_id,
        event_id=req.event_id,
    )
    _persist_case(case_id)
    return {"impact_point_id": ipid}


@router.post("/{case_id}/trajectories")
async def add_trajectory(case_id: str, req: AddTrajectoryRequest):
    case = _open_case(case_id)
    tid = case.add_trajectory(entity_id=req.entity_id, positions=req.positions)
    _persist_case(case_id)
    return {"trajectory_id": tid}


@router.get("/{case_id}/positions/{entity_id}")
async def get_positions(case_id: str, entity_id: str):
    return _open_case(case_id).get_positions_for_entity(entity_id)


@router.get("/{case_id}/impact-points")
async def get_impact_points(case_id: str):
    return _open_case(case_id).get_impact_points()


# ===================================================================
# EVIDENCE LAYER
# ===================================================================

@router.post("/{case_id}/sources")
async def add_source(case_id: str, req: AddSourceRequest):
    case = _open_case(case_id)
    sid = case.add_source(source_type=req.source_type, description=req.description)
    _persist_case(case_id)
    return {"source_id": sid}


@router.post("/{case_id}/evidence")
async def add_evidence(case_id: str, req: AddEvidenceRequest):
    case = _open_case(case_id)
    eid = case.add_evidence(
        category=req.category, key=req.key, value=req.value,
        unit=req.unit, confidence=req.confidence,
        source_type=req.source_type, source_id=req.source_id,
        applies_to_vehicle=req.applies_to_vehicle,
        applies_to_scene=req.applies_to_scene,
    )
    _persist_case(case_id)
    return {"evidence_id": eid}


@router.get("/{case_id}/evidence/{vehicle_number}")
async def get_evidence(case_id: str, vehicle_number: int):
    return _open_case(case_id).get_evidence_for_vehicle(vehicle_number)


@router.get("/{case_id}/gaps")
async def get_gaps(case_id: str):
    return _open_case(case_id).find_gaps()


@router.get("/{case_id}/contradictions")
async def get_contradictions(case_id: str):
    return _open_case(case_id).find_contradictions()


# ===================================================================
# CAUSAL LAYER
# ===================================================================

@router.post("/{case_id}/factors")
async def add_factor(case_id: str, req: AddFactorRequest):
    case = _open_case(case_id)
    fid = case.add_factor(
        factor_type=req.factor_type, description=req.description,
        severity=req.severity,
    )
    _persist_case(case_id)
    return {"factor_id": fid}


@router.post("/{case_id}/factors/link")
async def link_factor(case_id: str, req: LinkFactorRequest):
    """Link a factor to an event (CAUSED_BY), factor (CONTRIBUTED_TO), or evidence (SUPPORTED_BY)."""
    case = _open_case(case_id)
    if req.link_type == "caused_by":
        case.link_factor_to_event(req.factor_id, req.target_id)
    elif req.link_type == "contributed_to":
        case.link_factor_to_factor(req.factor_id, req.target_id)
    elif req.link_type == "supported_by":
        case.link_factor_to_evidence(req.factor_id, req.target_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown link_type: {req.link_type}")
    _persist_case(case_id)
    return {"status": "linked"}


@router.get("/{case_id}/factors")
async def get_factors(case_id: str):
    return _open_case(case_id).get_factors()


@router.get("/{case_id}/causal-chain")
async def get_causal_chain(case_id: str):
    return _open_case(case_id).get_causal_chain()


# ===================================================================
# PHYSICAL LAYER
# ===================================================================

@router.post("/{case_id}/delta-v")
async def add_delta_v(case_id: str, req: AddDeltaVRequest):
    case = _open_case(case_id)
    did = case.add_delta_v(
        vehicle_number=req.vehicle_number, dvx=req.dvx, dvy=req.dvy,
        magnitude_mph=req.magnitude_mph, event_id=req.event_id,
    )
    _persist_case(case_id)
    return {"deltav_id": did}


@router.post("/{case_id}/forces")
async def add_force(case_id: str, req: AddForceRequest):
    case = _open_case(case_id)
    fid = case.add_force(
        magnitude=req.magnitude, direction=req.direction,
        vehicle_number=req.vehicle_number,
        impact_point_id=req.impact_point_id, event_id=req.event_id,
    )
    _persist_case(case_id)
    return {"force_id": fid}


@router.post("/{case_id}/crush")
async def add_crush(case_id: str, req: AddCrushRequest):
    case = _open_case(case_id)
    cid = case.add_crush(
        vehicle_number=req.vehicle_number, depth=req.depth,
        width=req.width, profile=req.profile,
    )
    _persist_case(case_id)
    return {"crush_id": cid}


@router.post("/{case_id}/energy")
async def add_energy(case_id: str, req: AddEnergyRequest):
    case = _open_case(case_id)
    eid = case.add_energy(
        value=req.value, unit=req.unit, vehicle_number=req.vehicle_number,
    )
    _persist_case(case_id)
    return {"energy_id": eid}


@router.get("/{case_id}/physical/{vehicle_number}")
async def get_physical(case_id: str, vehicle_number: int):
    return _open_case(case_id).get_physical_for_vehicle(vehicle_number)


# ===================================================================
# CROSS-LAYER QUERIES
# ===================================================================

@router.get("/{case_id}/project")
async def project_to_pycrash(case_id: str):
    """Project evidence into pycrash simulation input dicts."""
    return _open_case(case_id).project_to_pycrash()


@router.get("/{case_id}/layers")
async def get_layer_summary(case_id: str):
    """Summary of all 6 graph layers."""
    return _open_case(case_id).get_layer_summary()


# ===================================================================
# EXPORT / IMPORT
# ===================================================================

@router.get("/{case_id}/export")
async def export_case(case_id: str):
    """Export case as portable .crash v2 format (JSON hypergraph)."""
    return _open_case(case_id).export()


@router.post("/import")
async def import_crash_file(file: UploadFile = File(...)):
    """Import a .crash file into a new case hypergraph."""
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid .crash file")

    store = _get_store()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".crash", delete=False) as f:
        json.dump(data, f)
        tmp_path = f.name

    try:
        from crashout.graph.store import InMemoryCaseGraph
        case = InMemoryCaseGraph.import_crash_file(tmp_path, store)
        return {"case_id": case.case_id, "title": case.title}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {e}")
    finally:
        import os
        os.unlink(tmp_path)
