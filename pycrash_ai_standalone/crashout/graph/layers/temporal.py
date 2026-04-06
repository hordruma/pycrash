from __future__ import annotations

import uuid
from typing import Any, Dict, List


class TemporalLayerMixin:
    """Temporal layer: events, phases, timeline ordering."""

    # Mixin assumes host class provides:
    #   self.case_id: str
    #   self._nodes: Dict[str, Dict[str, Any]]
    #   self._edges: List[Dict[str, Any]]

    def add_event(
        self,
        event_type: str,
        description: str = "",
        t: float | None = None,
        phase: str | None = None,
    ) -> str:
        """Add a discrete event to the timeline. Returns event_id."""
        event_id = f"{self.case_id}_evt_{uuid.uuid4().hex[:6]}"
        self._nodes[event_id] = {
            "id": event_id,
            "label": "Event",
            "layer": "temporal",
            "props": {"event_type": event_type, "description": description, "t": t},
        }
        # Auto-link to phase if provided
        if phase:
            phase_nodes = [
                n
                for n in self._nodes.values()
                if n["label"] == "Phase" and n["props"].get("phase_name") == phase
            ]
            if phase_nodes:
                self._edges.append(
                    {
                        "type": "BELONGS_TO_PHASE",
                        "from": event_id,
                        "to": phase_nodes[0]["id"],
                        "props": {},
                    }
                )
        return event_id

    def add_phase(
        self,
        phase_name: str,
        t_start: float | None = None,
        t_end: float | None = None,
    ) -> str:
        """Add a crash phase (pre_impact, first_contact, etc). Returns phase_id."""
        phase_id = f"{self.case_id}_phase_{phase_name}"
        self._nodes[phase_id] = {
            "id": phase_id,
            "label": "Phase",
            "layer": "temporal",
            "props": {"phase_name": phase_name, "t_start": t_start, "t_end": t_end},
        }
        return phase_id

    def link_event_to_phase(self, event_id: str, phase_id: str) -> None:
        """Link an event to a phase."""
        self._edges.append(
            {"type": "BELONGS_TO_PHASE", "from": event_id, "to": phase_id, "props": {}}
        )

    def order_events(self, event_id_before: str, event_id_after: str) -> None:
        """Establish temporal ordering: event_before PRECEDED_BY event_after."""
        self._edges.append(
            {"type": "PRECEDED_BY", "from": event_id_after, "to": event_id_before, "props": {}}
        )
        self._edges.append(
            {"type": "FOLLOWED_BY", "from": event_id_before, "to": event_id_after, "props": {}}
        )

    def link_entity_to_event(self, entity_id: str, event_id: str) -> None:
        """Cross-layer: entity PARTICIPATED_IN event."""
        self._edges.append(
            {"type": "PARTICIPATED_IN", "from": entity_id, "to": event_id, "props": {}}
        )

    def get_timeline(self) -> list:
        """Get all events in temporal order (by t, then by ordering edges)."""
        events = [
            {"event_id": n["id"], **n["props"]}
            for n in self._nodes.values()
            if n["label"] == "Event"
        ]
        # Sort by t if available, then stable sort by ordering edges
        events.sort(key=lambda e: (e.get("t") if e.get("t") is not None else float("inf")))
        return events

    def get_events_for_phase(self, phase_name: str) -> list:
        """Get all events belonging to a specific phase."""
        # Find phase node
        phase_nodes = [
            n
            for n in self._nodes.values()
            if n["label"] == "Phase" and n["props"].get("phase_name") == phase_name
        ]
        if not phase_nodes:
            return []
        phase_id = phase_nodes[0]["id"]
        # Find events linked to this phase
        event_ids = {
            e["from"]
            for e in self._edges
            if e["type"] == "BELONGS_TO_PHASE" and e["to"] == phase_id
        }
        return [
            {"event_id": n["id"], **n["props"]}
            for n in self._nodes.values()
            if n["id"] in event_ids
        ]
