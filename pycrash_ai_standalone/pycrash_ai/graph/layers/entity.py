"""Entity layer mixin for the crash reconstruction hypergraph.

Provides methods to add and query entities (vehicles, drivers, pedestrians,
fixed objects) that participate in a crash event.  Mixed into
``InMemoryCaseGraph``.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


class EntityLayerMixin:
    """Entity layer: vehicles, drivers, pedestrians, objects."""

    # -- Declared for type-checkers; actual attributes live on the host class --
    case_id: str
    _nodes: Dict[str, Dict[str, Any]]
    _edges: List[Dict[str, Any]]

    # --------------------------------------------------------------------- #
    #  Vehicles                                                              #
    # --------------------------------------------------------------------- #

    def add_vehicle(
        self,
        vehicle_number: int,
        make: Optional[str] = None,
        model: Optional[str] = None,
        year: Optional[int] = None,
        role: str = "unknown",
    ) -> str:
        """Add a vehicle entity.

        Parameters
        ----------
        vehicle_number : int
            Sequential vehicle identifier (1, 2, ...).
        make, model : str, optional
            Vehicle make and model.  Default ``"Unknown"``.
        year : int, optional
            Model year.  Default ``0``.
        role : str
            Role in the crash (e.g. ``"striking"``, ``"struck"``).

        Returns
        -------
        str
            ``'{case_id}_v{vehicle_number}'``
        """
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        self._nodes[vehicle_id] = {
            "id": vehicle_id,
            "label": "Vehicle",
            "layer": "entity",
            "props": {
                "vehicle_number": vehicle_number,
                "year": year or 0,
                "make": make or "Unknown",
                "model": model or "Unknown",
                "role": role,
            },
        }
        self._edges.append({
            "type": "INVOLVED_IN",
            "from": vehicle_id,
            "to": f"{self.case_id}_case",
            "props": {},
        })
        return vehicle_id

    # --------------------------------------------------------------------- #
    #  Drivers                                                               #
    # --------------------------------------------------------------------- #

    def add_driver(
        self,
        vehicle_number: int,
        name: Optional[str] = None,
        age: Optional[int] = None,
        impairment: Optional[str] = None,
    ) -> str:
        """Add a driver linked to a vehicle.

        Parameters
        ----------
        vehicle_number : int
            The vehicle number the driver was operating.
        name : str, optional
            Driver name.  Default ``"Unknown"``.
        age : int, optional
            Driver age.
        impairment : str, optional
            Known impairment (e.g. ``"alcohol"``).

        Returns
        -------
        str
            ``'{case_id}_d{vehicle_number}'``
        """
        driver_id = f"{self.case_id}_d{vehicle_number}"
        self._nodes[driver_id] = {
            "id": driver_id,
            "label": "Driver",
            "layer": "entity",
            "props": {
                "name": name or "Unknown",
                "age": age,
                "impairment": impairment,
                "vehicle_number": vehicle_number,
            },
        }
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        self._edges.append({
            "type": "DRIVEN_BY",
            "from": vehicle_id,
            "to": driver_id,
            "props": {},
        })
        return driver_id

    # --------------------------------------------------------------------- #
    #  Fixed objects                                                         #
    # --------------------------------------------------------------------- #

    def add_object(
        self,
        object_type: str,
        description: str = "",
    ) -> str:
        """Add a fixed object (pole, guardrail, tree, etc.).

        Parameters
        ----------
        object_type : str
            Category of the object (e.g. ``"pole"``, ``"tree"``).
        description : str
            Free-text description.

        Returns
        -------
        str
            ``'{case_id}_obj_{hex}'`` with a short unique suffix.
        """
        object_id = f"{self.case_id}_obj_{uuid.uuid4().hex[:6]}"
        self._nodes[object_id] = {
            "id": object_id,
            "label": "Object",
            "layer": "entity",
            "props": {
                "object_type": object_type,
                "description": description,
            },
        }
        return object_id

    # --------------------------------------------------------------------- #
    #  Queries                                                               #
    # --------------------------------------------------------------------- #

    def get_vehicles(self) -> List[Dict[str, Any]]:
        """Return all vehicles sorted by ``vehicle_number``."""
        vehicles = [
            {"vehicle_id": n["id"], **n["props"]}
            for n in self._nodes.values()
            if n["label"] == "Vehicle"
        ]
        return sorted(vehicles, key=lambda v: v.get("vehicle_number", 0))

    def get_drivers(self) -> List[Dict[str, Any]]:
        """Return all drivers."""
        return [
            {"driver_id": n["id"], **n["props"]}
            for n in self._nodes.values()
            if n["label"] == "Driver"
        ]
