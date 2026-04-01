"""Vehicle database lookup routes."""
from __future__ import annotations

import json
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from pycrash_ai.api.models import VehicleLookupResponse

router = APIRouter()

# Load vehicle database
_VEHICLE_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "vehicles.json")
_VEHICLES: List[dict] = []


def _load_db():
    global _VEHICLES
    if not _VEHICLES and os.path.exists(_VEHICLE_DB_PATH):
        with open(_VEHICLE_DB_PATH) as f:
            _VEHICLES = json.load(f)


@router.get("/vehicles/lookup", response_model=List[VehicleLookupResponse])
def lookup_vehicle(
    year: Optional[int] = Query(None),
    make: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    """Look up vehicle specifications by year/make/model.

    Returns matching vehicles from the built-in database.
    All dimensions in imperial units (lb, ft).
    """
    _load_db()

    results = _VEHICLES
    if year:
        results = [v for v in results if v.get("year") == year]
    if make:
        results = [v for v in results if v.get("make", "").lower() == make.lower()]
    if model:
        results = [v for v in results if v.get("model", "").lower() == model.lower()]

    if not results:
        raise HTTPException(404, f"No vehicle found for {year} {make} {model}")

    return [VehicleLookupResponse(**v) for v in results[:10]]


@router.get("/vehicles/makes", response_model=List[str])
def list_makes():
    """List all vehicle makes in the database."""
    _load_db()
    return sorted(set(v.get("make", "") for v in _VEHICLES))
