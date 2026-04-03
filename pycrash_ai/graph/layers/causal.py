from __future__ import annotations

import uuid


class CausalLayerMixin:
    """Causal layer: contributing factors and causal chains."""

    def add_factor(self, factor_type: str, description: str = "", severity: float = 0.5) -> str:
        """Add a contributing factor (distraction, excessive_speed, etc)."""
        factor_id = f"{self.case_id}_fac_{uuid.uuid4().hex[:6]}"
        self._nodes[factor_id] = {
            "id": factor_id, "label": "Factor", "layer": "causal",
            "props": {"factor_type": factor_type, "description": description, "severity": severity},
        }
        return factor_id

    def link_factor_to_event(self, factor_id: str, event_id: str) -> None:
        """Cross-layer: factor CAUSED_BY -> event."""
        self._edges.append({"type": "CAUSED_BY", "from": event_id, "to": factor_id, "props": {}})

    def link_factor_to_factor(self, cause_id: str, effect_id: str) -> None:
        """Causal chain: cause CONTRIBUTED_TO effect."""
        self._edges.append({"type": "CONTRIBUTED_TO", "from": cause_id, "to": effect_id, "props": {}})

    def link_factor_to_evidence(self, factor_id: str, evidence_id: str) -> None:
        """Cross-layer: factor SUPPORTED_BY evidence."""
        self._edges.append({"type": "SUPPORTED_BY", "from": factor_id, "to": evidence_id, "props": {}})

    def get_factors(self) -> list:
        """Get all contributing factors."""
        return [
            {"factor_id": n["id"], **n["props"]}
            for n in self._nodes.values() if n["label"] == "Factor"
        ]

    def get_causal_chain(self) -> list:
        """Get the full causal chain: factors with their connections."""
        factors = self.get_factors()

        # Enrich each factor with its connections
        for fac in factors:
            fid = fac["factor_id"]
            # What events this factor caused
            fac["caused_events"] = [
                e["from"] for e in self._edges
                if e["type"] == "CAUSED_BY" and e["to"] == fid
            ]
            # What factors this contributed to
            fac["contributed_to"] = [
                e["to"] for e in self._edges
                if e["type"] == "CONTRIBUTED_TO" and e["from"] == fid
            ]
            # What factors contributed to this
            fac["caused_by"] = [
                e["from"] for e in self._edges
                if e["type"] == "CONTRIBUTED_TO" and e["to"] == fid
            ]
            # Supporting evidence
            fac["supporting_evidence"] = [
                e["to"] for e in self._edges
                if e["type"] == "SUPPORTED_BY" and e["from"] == fid
            ]

        return factors

    def trace_causal_chain(self, factor_id: str) -> dict:
        """Trace the full causal chain from a factor through events to physical outcomes.

        Cross-layer traversal: Factor -> Events -> Physical (delta-V, forces)
        """
        result = {"factor_id": factor_id, "chain": []}

        factor_node = self._nodes.get(factor_id)
        if not factor_node:
            return result

        result["factor_type"] = factor_node["props"].get("factor_type")
        result["severity"] = factor_node["props"].get("severity")

        # Find events caused by this factor
        event_ids = [e["from"] for e in self._edges if e["type"] == "CAUSED_BY" and e["to"] == factor_id]

        for eid in event_ids:
            event_node = self._nodes.get(eid)
            if not event_node:
                continue

            step = {
                "event_id": eid,
                "event_type": event_node["props"].get("event_type"),
                "physical_outcomes": [],
            }

            # Find physical outcomes from this event (PRODUCED edges)
            phys_ids = [e["to"] for e in self._edges if e["type"] == "PRODUCED" and e["from"] == eid]
            for pid in phys_ids:
                phys_node = self._nodes.get(pid)
                if phys_node:
                    step["physical_outcomes"].append({
                        "id": pid, "label": phys_node["label"], **phys_node["props"],
                    })

            result["chain"].append(step)

        # Also find downstream factors (CONTRIBUTED_TO)
        downstream = [e["to"] for e in self._edges if e["type"] == "CONTRIBUTED_TO" and e["from"] == factor_id]
        result["downstream_factors"] = downstream

        return result

    def get_evidence_supporting_factor(self, factor_id: str) -> list:
        """Get all evidence linked to a causal factor. Cross-layer query."""
        ev_ids = [e["to"] for e in self._edges if e["type"] == "SUPPORTED_BY" and e["from"] == factor_id]
        return [
            {"evidence_id": n["id"], **n["props"]}
            for n in self._nodes.values()
            if n["id"] in ev_ids and n["label"] == "Evidence"
        ]
