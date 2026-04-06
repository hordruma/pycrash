"""6-layer crash reconstruction hypergraph store.

Composes six layer mixins into a unified case graph:
    Entity   → vehicles, drivers, objects
    Temporal → events, phases, timeline
    Spatial  → positions, trajectories, impact points
    Evidence → evidence, sources, contradictions, gaps
    Causal   → contributing factors, causal chains
    Physical → delta-V, forces, crush, energy

Two implementations:
    InMemoryCaseGraph  — fully functional, no external deps (testing/local)
    CaseGraph          — FalkorDB-backed (production with Docker)

Usage:
    store = get_store()
    case = store.create_case("Case-001", "Camry vs Civic rear-end")
    case.add_vehicle(1, "Toyota", "Camry", 2020, role="striking")
    case.add_event("first_contact", "Front of V1 to rear of V2", t=0.0)
    case.add_factor("excessive_speed", severity=0.8)
    case.add_delta_v(1, dvx=-15.2, dvy=0.0)
    gaps = case.find_gaps()
    sim_input = case.project_to_pycrash()
    case.export("case_001.crash")
"""
from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from crashout.graph.schema import (
    GraphLayer, NodeLabel, EVIDENCE_TO_PYCRASH,
)
from crashout.graph.layers.entity import EntityLayerMixin
from crashout.graph.layers.temporal import TemporalLayerMixin
from crashout.graph.layers.spatial import SpatialLayerMixin
from crashout.graph.layers.evidence import EvidenceLayerMixin
from crashout.graph.layers.causal import CausalLayerMixin
from crashout.graph.layers.physical import PhysicalLayerMixin


# ===================================================================
# IN-MEMORY HYPERGRAPH (fully functional, no external deps)
# ===================================================================

class InMemoryCaseGraph(
    EntityLayerMixin,
    TemporalLayerMixin,
    SpatialLayerMixin,
    EvidenceLayerMixin,
    CausalLayerMixin,
    PhysicalLayerMixin,
):
    """In-memory 6-layer crash reconstruction hypergraph.

    All nodes live in self._nodes (dict keyed by node_id).
    All edges live in self._edges (list of dicts).
    Cross-layer edges are just edges connecting nodes from different layers.
    """

    def __init__(self, case_id: str, title: str = ""):
        self.case_id = case_id
        self.title = title
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: List[Dict[str, Any]] = []

        # Create the root Case node
        self._nodes[f"{case_id}_case"] = {
            "id": f"{case_id}_case",
            "label": "Case",
            "layer": "entity",
            "props": {"case_id": case_id, "title": title},
        }

    # ------------------------------------------------------------------
    # Cross-layer queries — the real power of the hypergraph
    # ------------------------------------------------------------------

    def project_to_pycrash(self) -> List[Dict[str, Any]]:
        """Project graph evidence into pycrash Vehicle input dicts.

        Traverses the evidence layer, picks the highest-confidence
        value for each parameter, maps through EVIDENCE_TO_PYCRASH,
        and builds dicts compatible with pycrash.Vehicle().
        """
        vehicles = self.get_vehicles()
        results = []

        for veh in vehicles:
            vn = veh["vehicle_number"]
            evidence = self.get_evidence_for_vehicle(vn)

            # Group by key, pick highest confidence
            best: Dict[str, Dict[str, Any]] = {}
            for e in evidence:
                key = e["key"]
                if key not in best or e["confidence"] > best[key]["confidence"]:
                    best[key] = e

            # Base input dict
            input_dict: Dict[str, Any] = {
                "year": veh.get("year", 0),
                "make": veh.get("make", "Unknown"),
                "model": veh.get("model", "Unknown"),
                "striking": veh.get("role") == "striking",
                "init_x_pos": 0, "init_y_pos": 0,
                "head_angle": 0, "vy_initial": 0,
                "omega_z": 0, "brake": 0,
                "steer_ratio": 16, "vin": "",
            }

            # Apply evidence through mapping
            for key, ev in best.items():
                val = ev["value_numeric"] if ev["value_numeric"] != 0 else ev["value"]
                if key in EVIDENCE_TO_PYCRASH:
                    pycrash_key, converter = EVIDENCE_TO_PYCRASH[key]
                    try:
                        input_dict[pycrash_key] = converter(val)
                    except (ValueError, TypeError):
                        pass

            results.append({
                "vehicle_number": vn,
                "vehicle_id": veh["vehicle_id"],
                "role": veh.get("role", "unknown"),
                "input_dict": input_dict,
                "evidence_count": len(evidence),
                "confidence_avg": (
                    sum(e["confidence"] for e in evidence) / len(evidence)
                    if evidence else 0.0
                ),
            })

        return results

    def get_full_timeline(self) -> List[Dict[str, Any]]:
        """Full timeline with positions, factors, and evidence at each event.

        Cross-layer traversal: Temporal → Spatial + Causal + Evidence
        """
        events = self.get_timeline()
        for event in events:
            eid = event["event_id"]

            # Spatial: where did this event occur?
            pos_ids = {
                e["to"] for e in self._edges
                if e["type"] == "OCCURRED_AT" and e["from"] == eid
            }
            event["positions"] = [
                {"id": n["id"], **n["props"]}
                for n in self._nodes.values()
                if n["id"] in pos_ids
            ]

            # Causal: what factors caused this event?
            fac_ids = {
                e["to"] for e in self._edges
                if e["type"] == "CAUSED_BY" and e["from"] == eid
            }
            event["factors"] = [
                {"id": n["id"], **n["props"]}
                for n in self._nodes.values()
                if n["id"] in fac_ids
            ]

            # Entity: who participated?
            entity_ids = {
                e["from"] for e in self._edges
                if e["type"] == "PARTICIPATED_IN" and e["to"] == eid
            }
            event["participants"] = [
                {"id": n["id"], "label": n["label"], **n["props"]}
                for n in self._nodes.values()
                if n["id"] in entity_ids
            ]

            # Physical: what did this event produce?
            phys_ids = {
                e["to"] for e in self._edges
                if e["type"] == "PRODUCED" and e["from"] == eid
            }
            event["physical_outcomes"] = [
                {"id": n["id"], "label": n["label"], **n["props"]}
                for n in self._nodes.values()
                if n["id"] in phys_ids
            ]

        return events

    def get_layer_summary(self) -> Dict[str, Any]:
        """Summary of all 6 graph layers: node counts, edge counts."""
        layer_nodes: Dict[str, int] = {}
        for n in self._nodes.values():
            layer = n.get("layer", "unknown")
            layer_nodes[layer] = layer_nodes.get(layer, 0) + 1

        # Count cross-layer vs intra-layer edges
        cross_layer_count = 0
        intra_layer_count = 0
        for e in self._edges:
            from_node = self._nodes.get(e["from"])
            to_node = self._nodes.get(e["to"])
            if from_node and to_node:
                if from_node.get("layer") != to_node.get("layer"):
                    cross_layer_count += 1
                else:
                    intra_layer_count += 1

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "cross_layer_edges": cross_layer_count,
            "intra_layer_edges": intra_layer_count,
            "layers": {
                layer: {
                    "node_count": layer_nodes.get(layer, 0),
                }
                for layer in ["entity", "temporal", "spatial",
                              "evidence", "causal", "physical"]
            },
        }

    # ------------------------------------------------------------------
    # Export / Import (.crash v2 format)
    # ------------------------------------------------------------------

    def export(self, filepath: str = None) -> Dict[str, Any]:
        """Export the full hypergraph as a portable .crash v2 file.

        Contains all 6 layers: nodes, edges, projection, gaps,
        contradictions, timeline — everything to reconstruct or share.
        """
        vehicles = self.get_vehicles()
        projection = self.project_to_pycrash()

        # Collect all evidence by vehicle
        all_evidence = []
        for veh in vehicles:
            for e in self.get_evidence_for_vehicle(veh["vehicle_number"]):
                all_evidence.append(e)

        export_data = {
            "format": "pycrash_case",
            "version": "2.0",
            "case_id": self.case_id,
            "title": self.title,
            # Entity layer
            "vehicles": vehicles,
            "drivers": self.get_drivers(),
            # Temporal layer
            "timeline": self.get_timeline(),
            # Evidence layer
            "evidence": all_evidence,
            "contradictions": self.find_contradictions(),
            "gaps": self.find_gaps(),
            # Causal layer
            "factors": self.get_factors(),
            "causal_chain": self.get_causal_chain(),
            # Physical layer
            "physical": {
                veh["vehicle_number"]: self.get_physical_for_vehicle(
                    veh["vehicle_number"]
                )
                for veh in vehicles
            },
            # Spatial layer
            "impact_points": self.get_impact_points(),
            # Cross-layer
            "projection": projection,
            "layer_summary": self.get_layer_summary(),
            # Raw graph (for full fidelity reimport)
            "_nodes": list(self._nodes.values()),
            "_edges": self._edges,
        }

        if filepath:
            with open(filepath, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

        return export_data

    @classmethod
    def import_crash_file(cls, filepath: str, store: Any) -> 'InMemoryCaseGraph':
        """Import a .crash file into a new case graph.

        Supports both v1 (flat) and v2 (hypergraph) formats.
        """
        with open(filepath) as f:
            data = json.load(f)

        case = store.create_case(
            case_id=data["case_id"],
            title=data.get("title", ""),
        )
        case.add_scene()

        # Check for v2 raw graph data (full fidelity)
        if "_nodes" in data and "_edges" in data:
            # Reimport raw graph
            for node in data["_nodes"]:
                case._nodes[node["id"]] = node
            case._edges = data["_edges"]
            return case

        # v1 fallback: reconstruct from structured data
        for veh in data.get("vehicles", []):
            case.add_vehicle(
                vehicle_number=veh.get("vehicle_number", 1),
                make=veh.get("make"), model=veh.get("model"),
                year=veh.get("year"), role=veh.get("role", "unknown"),
            )

        for ev in data.get("evidence", []):
            case.add_evidence(
                category=ev["category"], key=ev["key"],
                value=ev.get("value_numeric", ev["value"]),
                unit=ev.get("unit", ""),
                confidence=ev.get("confidence", 0.5),
                source_type=ev.get("source_type", "analyst"),
                applies_to_vehicle=ev.get("vehicle_number"),
            )

        for fac in data.get("factors", []):
            case.add_factor(
                factor_type=fac.get("factor_type", "unknown"),
                description=fac.get("description", ""),
                severity=fac.get("severity", 0.5),
            )

        return case


# ===================================================================
# IN-MEMORY STORE
# ===================================================================

class InMemoryCaseStore:
    """In-memory store for testing without FalkorDB.

    Optionally persists cases to disk as JSON files when ``data_dir``
    is set (via constructor or the ``PYCRASH_CASES_DIR`` env var).
    On startup, any ``.json`` files in that directory are loaded back
    into memory so cases survive container restarts.
    """

    def __init__(self, data_dir: str = ""):
        self._cases: Dict[str, InMemoryCaseGraph] = {}
        self._data_dir = data_dir or os.getenv("PYCRASH_CASES_DIR", "")
        if self._data_dir:
            os.makedirs(self._data_dir, exist_ok=True)
            self._load_all()

    @property
    def connected(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Load all cases from disk on startup."""
        if not self._data_dir:
            return
        for path in glob.glob(os.path.join(self._data_dir, "*.json")):
            try:
                with open(path) as f:
                    data = json.load(f)
                case_id = data.get("case_id", "")
                if not case_id:
                    continue
                case = InMemoryCaseGraph(case_id, data.get("title", ""))
                # Restore raw graph if available (full fidelity)
                if "_nodes" in data and "_edges" in data:
                    for node in data["_nodes"]:
                        case._nodes[node["id"]] = node
                    case._edges = data["_edges"]
                logger.info("Loaded case %s from %s", case_id, path)
                self._cases[case_id] = case
            except Exception:
                logger.warning("Failed to load case from %s", path, exc_info=True)

    def _persist(self, case_id: str) -> None:
        """Save a case to disk."""
        if not self._data_dir or case_id not in self._cases:
            return
        try:
            export = self._cases[case_id].export()
            path = os.path.join(self._data_dir, f"{case_id}.json")
            with open(path, "w") as f:
                json.dump(export, f, indent=2, default=str)
        except Exception:
            logger.warning("Failed to persist case %s", case_id, exc_info=True)

    def save_case(self, case_id: str) -> None:
        """Explicitly save a case to disk."""
        self._persist(case_id)

    def load_case(self, case_id: str) -> InMemoryCaseGraph:
        """Load (or reload) a single case from disk."""
        if not self._data_dir:
            raise FileNotFoundError("No data_dir configured for persistence")
        path = os.path.join(self._data_dir, f"{case_id}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No persisted case file: {path}")
        with open(path) as f:
            data = json.load(f)
        case = InMemoryCaseGraph(case_id, data.get("title", ""))
        if "_nodes" in data and "_edges" in data:
            for node in data["_nodes"]:
                case._nodes[node["id"]] = node
            case._edges = data["_edges"]
        self._cases[case_id] = case
        return case

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_case(self, case_id: str, title: str = "",
                    date_of_loss: str = "") -> InMemoryCaseGraph:
        case = InMemoryCaseGraph(case_id, title)
        self._cases[case_id] = case
        self._persist(case_id)
        return case

    def open_case(self, case_id: str) -> InMemoryCaseGraph:
        if case_id not in self._cases:
            raise KeyError(f"Case not found: {case_id}")
        return self._cases[case_id]

    def list_cases(self) -> List[str]:
        return list(self._cases.keys())


# ===================================================================
# FALKORDB-BACKED GRAPH (production)
# ===================================================================

class CaseGraph:
    """FalkorDB-backed case graph. Supports entity and evidence layers.

    Temporal, spatial, causal, and physical layers use the same
    interface but delegate to FalkorDB Cypher queries.
    """

    def __init__(self, graph: Any, case_id: str, title: str = ""):
        self._graph = graph
        self.case_id = case_id
        self.title = title

    # Entity layer (FalkorDB)
    def add_vehicle(self, vehicle_number, make=None, model=None,
                    year=None, role="unknown"):
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        self._graph.query(
            "MATCH (c:Case {case_id: $cid}) "
            "CREATE (v:Vehicle {vehicle_id: $vid, vehicle_number: $vn, "
            "year: $y, make: $m, model: $mod, role: $r})"
            "-[:INVOLVED_IN]->(c)",
            params={"cid": self.case_id, "vid": vehicle_id,
                    "vn": vehicle_number, "y": year or 0,
                    "m": make or "Unknown", "mod": model or "Unknown",
                    "r": role},
        )
        return vehicle_id

    def add_scene(self):
        scene_id = f"{self.case_id}_scene"
        self._graph.query(
            "MATCH (c:Case {case_id: $cid}) "
            "CREATE (s:Scene {scene_id: $sid})-[:APPLIES_TO]->(c)",
            params={"cid": self.case_id, "sid": scene_id},
        )
        return scene_id

    def get_vehicles(self):
        result = self._graph.query(
            "MATCH (v:Vehicle)-[:INVOLVED_IN]->(:Case {case_id: $cid}) "
            "RETURN v.vehicle_id, v.vehicle_number, v.year, v.make, v.model, v.role "
            "ORDER BY v.vehicle_number",
            params={"cid": self.case_id},
        )
        return [
            {"vehicle_id": r[0], "vehicle_number": r[1], "year": r[2],
             "make": r[3], "model": r[4], "role": r[5]}
            for r in result.result_set
        ]

    # Stub methods for layers not yet implemented in FalkorDB
    def add_driver(self, *a, **kw):
        raise NotImplementedError("FalkorDB driver ops pending")

    def get_drivers(self):
        return []

    def add_event(self, *a, **kw):
        raise NotImplementedError("FalkorDB temporal ops pending")

    def add_phase(self, *a, **kw):
        raise NotImplementedError("FalkorDB temporal ops pending")

    def get_timeline(self):
        return []

    def add_position(self, *a, **kw):
        raise NotImplementedError("FalkorDB spatial ops pending")

    def add_impact_point(self, *a, **kw):
        raise NotImplementedError("FalkorDB spatial ops pending")

    def get_impact_points(self):
        return []

    def add_source(self, source_type, description=""):
        raise NotImplementedError("FalkorDB evidence ops pending")

    def add_evidence(self, **kw):
        raise NotImplementedError("FalkorDB evidence ops pending")

    def get_evidence_for_vehicle(self, vn):
        return []

    def find_contradictions(self):
        return []

    def find_gaps(self):
        return []

    def add_factor(self, *a, **kw):
        raise NotImplementedError("FalkorDB causal ops pending")

    def get_factors(self):
        return []

    def get_causal_chain(self):
        return []

    def add_delta_v(self, *a, **kw):
        raise NotImplementedError("FalkorDB physical ops pending")

    def add_force(self, *a, **kw):
        raise NotImplementedError("FalkorDB physical ops pending")

    def add_crush(self, *a, **kw):
        raise NotImplementedError("FalkorDB physical ops pending")

    def add_energy(self, *a, **kw):
        raise NotImplementedError("FalkorDB physical ops pending")

    def get_physical_for_vehicle(self, vn):
        return {"delta_v": [], "forces": [], "crush": [], "energy": []}

    def project_to_pycrash(self):
        return []

    def get_layer_summary(self):
        return {}

    def export(self, filepath=None):
        return {"format": "pycrash_case", "version": "2.0",
                "case_id": self.case_id, "title": self.title}


class CaseGraphStore:
    """Manages crash case graphs in FalkorDB."""

    def __init__(self, host="localhost", port=6379, redis_url=None):
        try:
            from falkordb import FalkorDB
            if redis_url:
                from urllib.parse import urlparse
                parsed = urlparse(redis_url)
                self._db = FalkorDB(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or 6379,
                )
            else:
                self._db = FalkorDB(host=host, port=port)
            self._connected = True
        except (ImportError, Exception):
            self._db = None
            self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def create_case(self, case_id, title="", date_of_loss=""):
        if not self._connected:
            raise RuntimeError("Not connected to FalkorDB")
        graph_name = f"case_{case_id.replace('-', '_').replace(' ', '_')}"
        graph = self._db.select_graph(graph_name)
        graph.query(
            "CREATE (c:Case {case_id: $cid, title: $t, date_of_loss: $d})",
            params={"cid": case_id, "t": title, "d": date_of_loss},
        )
        return CaseGraph(graph, case_id, title)

    def open_case(self, case_id):
        if not self._connected:
            raise RuntimeError("Not connected to FalkorDB")
        graph_name = f"case_{case_id.replace('-', '_').replace(' ', '_')}"
        graph = self._db.select_graph(graph_name)
        result = graph.query(
            "MATCH (c:Case {case_id: $cid}) RETURN c.title",
            params={"cid": case_id},
        )
        title = result.result_set[0][0] if result.result_set else ""
        return CaseGraph(graph, case_id, title)

    def list_cases(self):
        if not self._connected:
            return []
        return [g for g in self._db.list_graphs() if g.startswith("case_")]


# ===================================================================
# AUTO-DETECT STORE
# ===================================================================

def get_store(redis_url: Optional[str] = None, cases_dir: str = ""):
    """Get graph store. Tries FalkorDB first, falls back to in-memory.

    When falling back to the in-memory store, ``cases_dir`` (or the
    ``PYCRASH_CASES_DIR`` env var) enables disk persistence so that
    cases survive process restarts.
    """
    if redis_url:
        try:
            store = CaseGraphStore(redis_url=redis_url)
            if store.connected:
                return store
        except Exception:
            pass

    falkordb_url = os.getenv("FALKORDB_URL", "")
    if falkordb_url:
        try:
            store = CaseGraphStore(redis_url=falkordb_url)
            if store.connected:
                return store
        except Exception:
            pass

    resolved_dir = cases_dir or os.getenv("PYCRASH_CASES_DIR", "")
    return InMemoryCaseStore(data_dir=resolved_dir)
