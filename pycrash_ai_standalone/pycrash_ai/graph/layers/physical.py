"""Physical layer: forces, crush, energy, delta-V.

This is where pycrash simulation results live. Forces occur at impact
points (spatial), during events (temporal), applied to vehicles (entity).
"""
from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional


class PhysicalLayerMixin:
    """Physical layer: delta-V, forces, crush profiles, energy."""

    def add_delta_v(self, vehicle_number: int, dvx: float, dvy: float,
                    magnitude_mph: float = None, event_id: str = None) -> str:
        """Add a delta-V vector for a vehicle."""
        dv_id = f"{self.case_id}_dv_{uuid.uuid4().hex[:6]}"
        if magnitude_mph is None:
            mag_fps = math.sqrt(dvx**2 + dvy**2)
            magnitude_mph = round(mag_fps * 0.681818, 2)

        self._nodes[dv_id] = {
            "id": dv_id, "label": "DeltaV", "layer": "physical",
            "props": {
                "dvx": dvx, "dvy": dvy,
                "magnitude_fps": round(math.sqrt(dvx**2 + dvy**2), 4),
                "magnitude_mph": magnitude_mph,
                "vehicle_number": vehicle_number,
            },
        }
        # Cross-layer: vehicle EXPERIENCED delta-V
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        self._edges.append({
            "type": "EXPERIENCED", "from": vehicle_id, "to": dv_id, "props": {},
        })
        # Cross-layer: event PRODUCED delta-V
        if event_id:
            self._edges.append({
                "type": "PRODUCED", "from": event_id, "to": dv_id, "props": {},
            })
        return dv_id

    def add_force(self, magnitude: float, direction: float = 0.0,
                  vehicle_number: int = None, impact_point_id: str = None,
                  event_id: str = None) -> str:
        """Add an impact force vector."""
        force_id = f"{self.case_id}_force_{uuid.uuid4().hex[:6]}"
        self._nodes[force_id] = {
            "id": force_id, "label": "Force", "layer": "physical",
            "props": {
                "magnitude": magnitude, "direction": direction,
                "fx": magnitude * math.cos(math.radians(direction)),
                "fy": magnitude * math.sin(math.radians(direction)),
                "vehicle_number": vehicle_number,
            },
        }
        if vehicle_number is not None:
            vehicle_id = f"{self.case_id}_v{vehicle_number}"
            self._edges.append({
                "type": "EXPERIENCED", "from": vehicle_id, "to": force_id, "props": {},
            })
        if impact_point_id:
            self._edges.append({
                "type": "APPLIED_AT", "from": force_id, "to": impact_point_id, "props": {},
            })
        if event_id:
            self._edges.append({
                "type": "PRODUCED", "from": event_id, "to": force_id, "props": {},
            })
        return force_id

    def add_crush(self, vehicle_number: int, depth: float, width: float = 0.0,
                  profile: list = None) -> str:
        """Add crush data for a vehicle."""
        crush_id = f"{self.case_id}_crush_{uuid.uuid4().hex[:6]}"
        self._nodes[crush_id] = {
            "id": crush_id, "label": "Crush", "layer": "physical",
            "props": {
                "depth": depth, "width": width,
                "profile": profile or [],
                "vehicle_number": vehicle_number,
            },
        }
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        self._edges.append({
            "type": "EXPERIENCED", "from": vehicle_id, "to": crush_id, "props": {},
        })
        return crush_id

    def add_energy(self, value: float, unit: str = "ft-lb",
                   vehicle_number: int = None) -> str:
        """Add energy dissipation data."""
        energy_id = f"{self.case_id}_energy_{uuid.uuid4().hex[:6]}"
        self._nodes[energy_id] = {
            "id": energy_id, "label": "Energy", "layer": "physical",
            "props": {
                "value": value, "unit": unit,
                "vehicle_number": vehicle_number,
            },
        }
        if vehicle_number is not None:
            vehicle_id = f"{self.case_id}_v{vehicle_number}"
            self._edges.append({
                "type": "EXPERIENCED", "from": vehicle_id, "to": energy_id, "props": {},
            })
        return energy_id

    def get_physical_for_vehicle(self, vehicle_number: int) -> dict:
        """Get all physical data for a vehicle: delta-V, forces, crush, energy."""
        vehicle_id = f"{self.case_id}_v{vehicle_number}"

        # Find all nodes this vehicle EXPERIENCED
        phys_ids = {
            e["to"] for e in self._edges
            if e["type"] == "EXPERIENCED" and e["from"] == vehicle_id
        }

        result: Dict[str, List] = {
            "delta_v": [], "forces": [], "crush": [], "energy": [],
        }
        label_to_key = {
            "DeltaV": "delta_v", "Force": "forces",
            "Crush": "crush", "Energy": "energy",
        }

        for n in self._nodes.values():
            if n["id"] in phys_ids:
                key = label_to_key.get(n["label"])
                if key:
                    result[key].append({"id": n["id"], **n["props"]})

        return result
