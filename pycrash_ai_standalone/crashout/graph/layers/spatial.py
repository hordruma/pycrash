from __future__ import annotations

import uuid


class SpatialLayerMixin:
    """Spatial layer: positions, trajectories, impact points, geometry."""

    def add_position(self, x: float, y: float, heading: float = 0.0,
                     entity_id: str = None, event_id: str = None, t: float = None) -> str:
        """Add a position in space. Optionally link to entity and/or event."""
        pos_id = f"{self.case_id}_pos_{uuid.uuid4().hex[:6]}"
        self._nodes[pos_id] = {
            "id": pos_id, "label": "Position", "layer": "spatial",
            "props": {"x": x, "y": y, "heading": heading, "t": t},
        }
        if entity_id:
            # Cross-layer: entity AT_POSITION
            self._edges.append({"type": "AT_POSITION", "from": entity_id, "to": pos_id, "props": {"t": t}})
        if event_id:
            # Cross-layer: event OCCURRED_AT position
            self._edges.append({"type": "OCCURRED_AT", "from": event_id, "to": pos_id, "props": {}})
        return pos_id

    def add_impact_point(self, x: float, y: float, vehicle1_id: str, vehicle2_id: str,
                         event_id: str = None) -> str:
        """Add an impact point where two vehicles contacted."""
        ip_id = f"{self.case_id}_ip_{uuid.uuid4().hex[:6]}"
        self._nodes[ip_id] = {
            "id": ip_id, "label": "ImpactPoint", "layer": "spatial",
            "props": {"x": x, "y": y, "vehicle1_id": vehicle1_id, "vehicle2_id": vehicle2_id},
        }
        # Link vehicles to impact point
        self._edges.append({"type": "AT_POSITION", "from": vehicle1_id, "to": ip_id, "props": {"role": "striking"}})
        self._edges.append({"type": "AT_POSITION", "from": vehicle2_id, "to": ip_id, "props": {"role": "struck"}})
        if event_id:
            self._edges.append({"type": "OCCURRED_AT", "from": event_id, "to": ip_id, "props": {}})
        return ip_id

    def add_trajectory(self, entity_id: str, positions: list) -> str:
        """Add a trajectory (sequence of positions) for an entity.

        Args:
            entity_id: Vehicle or object this trajectory belongs to
            positions: List of dicts with {x, y, heading (opt), t (opt)}
        """
        traj_id = f"{self.case_id}_traj_{uuid.uuid4().hex[:6]}"
        self._nodes[traj_id] = {
            "id": traj_id, "label": "Trajectory", "layer": "spatial",
            "props": {"entity_id": entity_id, "point_count": len(positions)},
        }
        # Link entity to trajectory
        self._edges.append({"type": "AT_POSITION", "from": entity_id, "to": traj_id, "props": {}})

        # Create position nodes for each point and link to trajectory
        for i, pos in enumerate(positions):
            pos_id = f"{self.case_id}_tpos_{uuid.uuid4().hex[:6]}"
            self._nodes[pos_id] = {
                "id": pos_id, "label": "Position", "layer": "spatial",
                "props": {"x": pos.get("x", 0), "y": pos.get("y", 0),
                          "heading": pos.get("heading", 0), "t": pos.get("t"),
                          "seq": i},
            }
            self._edges.append({"type": "PART_OF_TRAJECTORY", "from": pos_id, "to": traj_id, "props": {"seq": i}})
            # Also cross-link entity to each position
            self._edges.append({"type": "AT_POSITION", "from": entity_id, "to": pos_id, "props": {"t": pos.get("t")}})

        return traj_id

    def get_positions_for_entity(self, entity_id: str) -> list:
        """Get all positions linked to an entity, sorted by time."""
        pos_ids = {e["to"] for e in self._edges if e["type"] == "AT_POSITION" and e["from"] == entity_id}
        positions = [
            {"position_id": n["id"], **n["props"]}
            for n in self._nodes.values()
            if n["id"] in pos_ids and n["label"] == "Position"
        ]
        positions.sort(key=lambda p: (p.get("t") if p.get("t") is not None else float("inf"), p.get("seq", 0)))
        return positions

    def get_impact_points(self) -> list:
        """Get all impact points."""
        return [
            {"impact_point_id": n["id"], **n["props"]}
            for n in self._nodes.values() if n["label"] == "ImpactPoint"
        ]
