from __future__ import annotations

import json
import uuid


def _is_numeric(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


class EvidenceLayerMixin:
    """Evidence layer: evidence nodes, sources, contradictions, gaps."""

    def add_scene(self) -> str:
        """Add a scene node to the case."""
        scene_id = f"{self.case_id}_scene"
        self._nodes[scene_id] = {
            "id": scene_id, "label": "Scene", "layer": "evidence",
            "props": {},
        }
        return scene_id

    def add_source(self, source_type: str, description: str = "") -> str:
        """Register an evidence source (police report, witness, EDR, etc)."""
        source_id = f"{self.case_id}_src_{uuid.uuid4().hex[:6]}"
        self._nodes[source_id] = {
            "id": source_id, "label": "Source", "layer": "evidence",
            "props": {"source_type": source_type, "description": description},
        }
        return source_id

    def add_evidence(self, category: str, key: str, value, unit: str = "",
                     confidence: float = 0.5, source_type: str = "analyst",
                     source_id: str = None, applies_to_vehicle: int = None,
                     applies_to_scene: bool = False) -> str:
        """Add a piece of evidence to the graph."""
        evidence_id = f"{self.case_id}_ev_{uuid.uuid4().hex[:6]}"

        if isinstance(value, (dict, list)):
            stored_value = json.dumps(value)
        else:
            stored_value = str(value)

        self._nodes[evidence_id] = {
            "id": evidence_id, "label": "Evidence", "layer": "evidence",
            "props": {
                "category": category, "key": key,
                "value": stored_value,
                "value_numeric": float(value) if _is_numeric(value) else 0.0,
                "unit": unit, "confidence": confidence,
                "source_type": source_type,
                "vehicle_number": applies_to_vehicle,
            },
        }

        if source_id and source_id in self._nodes:
            self._edges.append({"type": "OBSERVED", "from": source_id, "to": evidence_id, "props": {}})

        if applies_to_vehicle is not None:
            vehicle_id = f"{self.case_id}_v{applies_to_vehicle}"
            self._edges.append({"type": "APPLIES_TO", "from": evidence_id, "to": vehicle_id, "props": {}})

        if applies_to_scene:
            scene_id = f"{self.case_id}_scene"
            if scene_id in self._nodes:
                self._edges.append({"type": "APPLIES_TO", "from": evidence_id, "to": scene_id, "props": {}})

        return evidence_id

    def mark_contradiction(self, id1: str, id2: str, reason: str = "") -> None:
        self._edges.append({"type": "CONTRADICTS", "from": id1, "to": id2, "props": {"reason": reason}})

    def mark_supports(self, id1: str, id2: str) -> None:
        self._edges.append({"type": "SUPPORTS", "from": id1, "to": id2, "props": {}})

    def get_evidence_for_vehicle(self, vehicle_number: int) -> list:
        """Get all evidence applying to a specific vehicle."""
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        ev_ids = {e["from"] for e in self._edges if e["type"] == "APPLIES_TO" and e["to"] == vehicle_id}
        result = []
        for n in self._nodes.values():
            if n["id"] in ev_ids and n["label"] == "Evidence":
                entry = {
                    "evidence_id": n["id"],
                    "category": n["props"].get("category"),
                    "key": n["props"].get("key"),
                    "value": n["props"].get("value"),
                    "value_numeric": n["props"].get("value_numeric", 0.0),
                    "unit": n["props"].get("unit", ""),
                    "confidence": n["props"].get("confidence", 0.5),
                    "source_type": n["props"].get("source_type", ""),
                    "vehicle_number": vehicle_number,
                }
                result.append(entry)
        return result

    def find_contradictions(self) -> list:
        """Find same key, different value evidence on same vehicle."""
        # Group evidence by vehicle
        by_vehicle = {}
        for n in self._nodes.values():
            if n["label"] == "Evidence":
                vn = n["props"].get("vehicle_number")
                if vn is not None:
                    by_vehicle.setdefault(vn, []).append(n)

        contradictions = []
        for vn, evs in by_vehicle.items():
            by_key = {}
            for e in evs:
                by_key.setdefault(e["props"]["key"], []).append(e)
            for key, group in by_key.items():
                if len(group) > 1:
                    for i in range(len(group)):
                        for j in range(i + 1, len(group)):
                            if group[i]["props"]["value"] != group[j]["props"]["value"]:
                                contradictions.append({
                                    "key": key,
                                    "evidence_1": {"id": group[i]["id"], "value": group[i]["props"]["value"],
                                                   "confidence": group[i]["props"]["confidence"],
                                                   "source": group[i]["props"]["source_type"]},
                                    "evidence_2": {"id": group[j]["id"], "value": group[j]["props"]["value"],
                                                   "confidence": group[j]["props"]["confidence"],
                                                   "source": group[j]["props"]["source_type"]},
                                })
        return contradictions

    def find_gaps(self) -> list:
        """Find missing parameters needed for simulation."""
        from pycrash_ai.graph.schema import REQUIRED_VEHICLE_PARAMS

        gaps = []
        vehicles = [n for n in self._nodes.values() if n["label"] == "Vehicle"]
        for veh in vehicles:
            vn = veh["props"]["vehicle_number"]
            evidence = self.get_evidence_for_vehicle(vn)
            known = {e["key"] for e in evidence if e["category"] == "vehicle_spec"}
            missing = [p for p in REQUIRED_VEHICLE_PARAMS if p not in known]
            speed_ev = [e for e in evidence if e["category"] == "speed"]
            if not speed_ev:
                missing.append("estimated_speed")
            if missing:
                gaps.append({
                    "vehicle_id": veh["id"],
                    "make": veh["props"].get("make", "Unknown"),
                    "model": veh["props"].get("model", "Unknown"),
                    "missing": missing,
                })
        return gaps
