"""Case graph API routes - evidence space for crash reconstruction.

Manages the FalkorDB-backed case graph where extracted evidence lives,
contradictions are detected, gaps are identified, and simulation
parameters are projected from evidence.
"""
from __future__ import annotations

import json
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from pycrash_ai.api.graph.store import get_store

router = APIRouter(prefix="/cases", tags=["cases"])


# --- Request / Response models ---

class CreateCaseRequest(BaseModel):
    case_id: str = Field(..., min_length=1, description="Unique case identifier")
    title: str = Field("", description="Human-readable case title")
    date_of_loss: str = Field("", description="Date of the crash (YYYY-MM-DD)")


class AddVehicleRequest(BaseModel):
    vehicle_number: int = Field(..., ge=1, description="Vehicle number (1, 2, ...)")
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    role: str = Field("unknown", description="Role: striking, struck, unknown")


class AddEvidenceRequest(BaseModel):
    category: str = Field(..., description="Evidence category (speed, damage, vehicle_spec, ...)")
    key: str = Field(..., description="Parameter key (estimated_speed_mph, weight, ...)")
    value: Any = Field(..., description="Evidence value")
    unit: str = Field("", description="Unit of measurement")
    confidence: float = Field(0.5, ge=0, le=1, description="Confidence 0.0-1.0")
    source_type: str = Field("analyst", description="Source type (police_report, witness, edr, ...)")
    source_id: Optional[str] = None
    applies_to_vehicle: Optional[int] = Field(None, description="Vehicle number this applies to")
    applies_to_scene: bool = Field(False, description="Whether this applies to the scene")


class AddSourceRequest(BaseModel):
    source_type: str = Field(..., description="Source type (police_report, witness, edr, photo, ...)")
    description: str = Field("", description="Description of this source")


class CaseResponse(BaseModel):
    case_id: str
    title: str
    vehicles: List[Dict[str, Any]] = []
    evidence_count: int = 0


# --- Store singleton ---

_store = None


def _get_store():
    global _store
    if _store is None:
        _store = get_store()
    return _store


# --- Routes ---

@router.post("", response_model=CaseResponse)
async def create_case(req: CreateCaseRequest):
    """Create a new crash case graph."""
    store = _get_store()
    case = store.create_case(
        case_id=req.case_id,
        title=req.title,
        date_of_loss=req.date_of_loss,
    )
    case.add_scene()
    return CaseResponse(case_id=case.case_id, title=case.title)


@router.get("", response_model=List[str])
async def list_cases():
    """List all case IDs."""
    store = _get_store()
    return store.list_cases()


@router.get("/{case_id}")
async def get_case(case_id: str):
    """Get case overview with vehicles, evidence counts, and gaps."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception) as e:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

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
    }


@router.post("/{case_id}/vehicles")
async def add_vehicle(case_id: str, req: AddVehicleRequest):
    """Add a vehicle to the case."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    vehicle_id = case.add_vehicle(
        vehicle_number=req.vehicle_number,
        make=req.make,
        model=req.model,
        year=req.year,
        role=req.role,
    )
    return {"vehicle_id": vehicle_id}


@router.get("/{case_id}/vehicles")
async def get_vehicles(case_id: str):
    """Get all vehicles in a case."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case.get_vehicles()


@router.post("/{case_id}/sources")
async def add_source(case_id: str, req: AddSourceRequest):
    """Register an evidence source."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    source_id = case.add_source(
        source_type=req.source_type,
        description=req.description,
    )
    return {"source_id": source_id}


@router.post("/{case_id}/evidence")
async def add_evidence(case_id: str, req: AddEvidenceRequest):
    """Add a piece of evidence to the case graph."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    evidence_id = case.add_evidence(
        category=req.category,
        key=req.key,
        value=req.value,
        unit=req.unit,
        confidence=req.confidence,
        source_type=req.source_type,
        source_id=req.source_id,
        applies_to_vehicle=req.applies_to_vehicle,
        applies_to_scene=req.applies_to_scene,
    )
    return {"evidence_id": evidence_id}


@router.get("/{case_id}/evidence/{vehicle_number}")
async def get_evidence(case_id: str, vehicle_number: int):
    """Get all evidence for a specific vehicle."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case.get_evidence_for_vehicle(vehicle_number)


@router.get("/{case_id}/gaps")
async def get_gaps(case_id: str):
    """Find missing information needed for simulation."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case.find_gaps()


@router.get("/{case_id}/contradictions")
async def get_contradictions(case_id: str):
    """Find contradicting evidence in the case."""
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case.find_contradictions()


@router.get("/{case_id}/project")
async def project_to_pycrash(case_id: str):
    """Project case evidence into pycrash simulation input dicts.

    Traverses the evidence graph, picks the highest-confidence value
    for each parameter, and builds input dicts ready for pycrash.Vehicle().
    """
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case.project_to_pycrash()


@router.get("/{case_id}/export")
async def export_case(case_id: str):
    """Export case as portable .crash format (JSON).

    The .crash format contains all case data: vehicles, evidence,
    contradictions, gaps, and pycrash projection — everything needed
    to reconstruct or share a case.
    """
    store = _get_store()
    try:
        case = store.open_case(case_id)
    except (KeyError, Exception):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case.export()


@router.post("/import")
async def import_crash_file(file: UploadFile = File(..., description=".crash file")):
    """Import a .crash file into a new case graph."""
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid .crash file: not valid JSON")

    store = _get_store()

    # Write to temp file for import
    with tempfile.NamedTemporaryFile(mode="w", suffix=".crash", delete=False) as f:
        json.dump(data, f)
        tmp_path = f.name

    try:
        from pycrash_ai.api.graph.store import InMemoryCaseGraph
        case = InMemoryCaseGraph.import_crash_file(tmp_path, store)
        return {"case_id": case.case_id, "title": case.title}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {e}")
    finally:
        import os
        os.unlink(tmp_path)
