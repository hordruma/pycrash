"""FalkorDB-backed crash case graph store.

Each case is a graph within FalkorDB. Cases can be exported as portable
.crash files (JSON serialization of the full graph) and re-imported.

Usage:
    store = CaseGraphStore()  # connects to FalkorDB
    case = store.create_case("Case-001", "Camry vs Civic rear-end")
    case.add_vehicle(1, "Toyota", "Camry", 2020, role="striking")
    case.add_evidence("speed", "estimated_speed_mph", 35, "mph",
                      confidence=0.7, source_type="witness",
                      applies_to_vehicle=1)
    gaps = case.find_gaps()
    sim_input = case.project_to_pycrash()
    case.export("case_001.crash")
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pycrash_ai.api.graph.schema import (
    NodeLabel, EdgeType, EvidenceCategory, SourceType,
)


class CaseGraph:
    """A single crash case represented as a graph."""

    def __init__(self, graph: Any, case_id: str, title: str = ""):
        """
        Args:
            graph: FalkorDB graph object
            case_id: Unique case identifier
            title: Human-readable case title
        """
        self._graph = graph
        self.case_id = case_id
        self.title = title

    # ------------------------------------------------------------------
    # Vehicle operations
    # ------------------------------------------------------------------

    def add_vehicle(
        self,
        vehicle_number: int,
        make: Optional[str] = None,
        model: Optional[str] = None,
        year: Optional[int] = None,
        role: str = "unknown",
    ) -> str:
        """Add a vehicle to the case. Returns vehicle_id."""
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        self._graph.query(
            """
            MATCH (c:Case {case_id: $case_id})
            CREATE (v:Vehicle {
                vehicle_id: $vehicle_id,
                vehicle_number: $vehicle_number,
                year: $year,
                make: $make,
                model: $model_name,
                role: $role
            })
            CREATE (v)-[:INVOLVED_IN]->(c)
            """,
            params={
                "case_id": self.case_id,
                "vehicle_id": vehicle_id,
                "vehicle_number": vehicle_number,
                "year": year or 0,
                "make": make or "Unknown",
                "model_name": model or "Unknown",
                "role": role,
            },
        )
        return vehicle_id

    def add_source(
        self,
        source_type: str,
        description: str = "",
    ) -> str:
        """Register an evidence source (police report, witness, etc.)."""
        source_id = f"{self.case_id}_src_{uuid.uuid4().hex[:6]}"
        self._graph.query(
            """
            MATCH (c:Case {case_id: $case_id})
            CREATE (s:Source {
                source_id: $source_id,
                source_type: $source_type,
                description: $description
            })
            CREATE (s)-[:APPLIES_TO]->(c)
            """,
            params={
                "case_id": self.case_id,
                "source_id": source_id,
                "source_type": source_type,
                "description": description,
            },
        )
        return source_id

    def add_evidence(
        self,
        category: str,
        key: str,
        value: Any,
        unit: str = "",
        confidence: float = 0.5,
        source_type: str = "analyst",
        source_id: Optional[str] = None,
        applies_to_vehicle: Optional[int] = None,
        applies_to_scene: bool = False,
    ) -> str:
        """Add a piece of evidence to the graph.

        Args:
            category: Evidence category (speed, damage, vehicle_spec, etc.)
            key: Specific parameter (estimated_speed_mph, weight, surface, etc.)
            value: The evidence value
            unit: Unit of measurement
            confidence: 0.0-1.0 confidence in this evidence
            source_type: Where this came from
            source_id: Link to specific source node
            applies_to_vehicle: Vehicle number this applies to
            applies_to_scene: Whether this applies to the scene

        Returns:
            evidence_id
        """
        evidence_id = f"{self.case_id}_ev_{uuid.uuid4().hex[:6]}"

        # Serialize value for storage
        if isinstance(value, (dict, list)):
            stored_value = json.dumps(value)
        else:
            stored_value = str(value)

        self._graph.query(
            """
            CREATE (e:Evidence {
                evidence_id: $evidence_id,
                category: $category,
                key: $key,
                value: $value,
                value_numeric: $value_numeric,
                unit: $unit,
                confidence: $confidence,
                source_type: $source_type
            })
            """,
            params={
                "evidence_id": evidence_id,
                "category": category,
                "key": key,
                "value": stored_value,
                "value_numeric": float(value) if _is_numeric(value) else 0.0,
                "unit": unit,
                "confidence": confidence,
                "source_type": source_type,
            },
        )

        # Link to source
        if source_id:
            self._graph.query(
                """
                MATCH (s:Source {source_id: $source_id})
                MATCH (e:Evidence {evidence_id: $evidence_id})
                CREATE (s)-[:OBSERVED]->(e)
                """,
                params={"source_id": source_id, "evidence_id": evidence_id},
            )

        # Link to vehicle
        if applies_to_vehicle is not None:
            vehicle_id = f"{self.case_id}_v{applies_to_vehicle}"
            self._graph.query(
                """
                MATCH (e:Evidence {evidence_id: $evidence_id})
                MATCH (v:Vehicle {vehicle_id: $vehicle_id})
                CREATE (e)-[:APPLIES_TO]->(v)
                """,
                params={"evidence_id": evidence_id, "vehicle_id": vehicle_id},
            )

        # Link to scene
        if applies_to_scene:
            self._graph.query(
                """
                MATCH (e:Evidence {evidence_id: $evidence_id})
                MATCH (s:Scene)-[:APPLIES_TO]->(:Case {case_id: $case_id})
                CREATE (e)-[:APPLIES_TO]->(s)
                """,
                params={"evidence_id": evidence_id, "case_id": self.case_id},
            )

        return evidence_id

    def add_scene(self) -> str:
        """Add a scene node to the case."""
        scene_id = f"{self.case_id}_scene"
        self._graph.query(
            """
            MATCH (c:Case {case_id: $case_id})
            CREATE (s:Scene {scene_id: $scene_id})
            CREATE (s)-[:APPLIES_TO]->(c)
            """,
            params={"case_id": self.case_id, "scene_id": scene_id},
        )
        return scene_id

    def mark_contradiction(self, evidence_id_1: str, evidence_id_2: str,
                           reason: str = "") -> None:
        """Mark two pieces of evidence as contradicting each other."""
        self._graph.query(
            """
            MATCH (e1:Evidence {evidence_id: $id1})
            MATCH (e2:Evidence {evidence_id: $id2})
            CREATE (e1)-[:CONTRADICTS {reason: $reason}]->(e2)
            """,
            params={"id1": evidence_id_1, "id2": evidence_id_2, "reason": reason},
        )

    def mark_supports(self, evidence_id_1: str, evidence_id_2: str) -> None:
        """Mark two pieces of evidence as supporting each other."""
        self._graph.query(
            """
            MATCH (e1:Evidence {evidence_id: $id1})
            MATCH (e2:Evidence {evidence_id: $id2})
            CREATE (e1)-[:SUPPORTS]->(e2)
            """,
            params={"id1": evidence_id_1, "id2": evidence_id_2},
        )

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_vehicles(self) -> List[Dict[str, Any]]:
        """Get all vehicles in this case."""
        result = self._graph.query(
            """
            MATCH (v:Vehicle)-[:INVOLVED_IN]->(:Case {case_id: $case_id})
            RETURN v.vehicle_id, v.vehicle_number, v.year, v.make, v.model, v.role
            ORDER BY v.vehicle_number
            """,
            params={"case_id": self.case_id},
        )
        return [
            {
                "vehicle_id": row[0], "vehicle_number": row[1],
                "year": row[2], "make": row[3], "model": row[4], "role": row[5],
            }
            for row in result.result_set
        ]

    def get_evidence_for_vehicle(self, vehicle_number: int) -> List[Dict[str, Any]]:
        """Get all evidence applying to a specific vehicle."""
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        result = self._graph.query(
            """
            MATCH (e:Evidence)-[:APPLIES_TO]->(v:Vehicle {vehicle_id: $vehicle_id})
            RETURN e.evidence_id, e.category, e.key, e.value, e.value_numeric,
                   e.unit, e.confidence, e.source_type
            ORDER BY e.category, e.key
            """,
            params={"vehicle_id": vehicle_id},
        )
        return [
            {
                "evidence_id": row[0], "category": row[1], "key": row[2],
                "value": row[3], "value_numeric": row[4], "unit": row[5],
                "confidence": row[6], "source_type": row[7],
            }
            for row in result.result_set
        ]

    def find_contradictions(self) -> List[Dict[str, Any]]:
        """Find evidence that contradicts other evidence on the same entity."""
        result = self._graph.query(
            """
            MATCH (e1:Evidence)-[:APPLIES_TO]->(target)<-[:APPLIES_TO]-(e2:Evidence)
            WHERE e1.category = e2.category
              AND e1.key = e2.key
              AND e1.evidence_id < e2.evidence_id
              AND e1.value <> e2.value
            RETURN e1.evidence_id, e1.value, e1.confidence, e1.source_type,
                   e2.evidence_id, e2.value, e2.confidence, e2.source_type,
                   e1.key, labels(target)
            """,
        )
        return [
            {
                "key": row[8],
                "evidence_1": {"id": row[0], "value": row[1], "confidence": row[2], "source": row[3]},
                "evidence_2": {"id": row[4], "value": row[5], "confidence": row[6], "source": row[7]},
                "target_type": row[9],
            }
            for row in result.result_set
        ]

    def find_gaps(self) -> List[Dict[str, Any]]:
        """Find missing information needed for simulation.

        Checks each vehicle for required pycrash parameters.
        Returns list of {vehicle_id, make, model, missing_params}.
        """
        required_params = [
            "weight", "wb", "lcgf", "lcgr", "width", "length",
            "hcg", "track", "izz", "fwd", "rwd", "awd",
        ]

        vehicles = self.get_vehicles()
        gaps = []

        for veh in vehicles:
            evidence = self.get_evidence_for_vehicle(veh["vehicle_number"])
            known_keys = {e["key"] for e in evidence if e["category"] == "vehicle_spec"}
            missing = [p for p in required_params if p not in known_keys]

            # Also check for speed evidence
            speed_evidence = [e for e in evidence if e["category"] == "speed"]
            if not speed_evidence:
                missing.append("estimated_speed")

            if missing:
                gaps.append({
                    "vehicle_id": veh["vehicle_id"],
                    "make": veh["make"],
                    "model": veh["model"],
                    "missing": missing,
                })

        return gaps

    def project_to_pycrash(self) -> List[Dict[str, Any]]:
        """Project graph evidence into pycrash Vehicle input dicts.

        For each vehicle, collects the highest-confidence evidence
        for each parameter and builds a dict compatible with
        pycrash.Vehicle(name, input_dict=...).

        Returns list of input dicts (one per vehicle).
        """
        vehicles = self.get_vehicles()
        results = []

        for veh in vehicles:
            evidence = self.get_evidence_for_vehicle(veh["vehicle_number"])

            # Group by key, pick highest confidence for each
            best_evidence: Dict[str, Dict[str, Any]] = {}
            for e in evidence:
                key = e["key"]
                if key not in best_evidence or e["confidence"] > best_evidence[key]["confidence"]:
                    best_evidence[key] = e

            # Build pycrash input dict
            input_dict: Dict[str, Any] = {
                "year": veh["year"],
                "make": veh["make"],
                "model": veh["model"],
                "striking": veh["role"] == "striking",
                "init_x_pos": 0,
                "init_y_pos": 0,
                "head_angle": 0,
                "vy_initial": 0,
                "omega_z": 0,
                "brake": 0,
                "steer_ratio": 16,
                "vin": "",
            }

            # Map evidence keys to pycrash input dict keys
            for key, ev in best_evidence.items():
                val = ev["value_numeric"] if ev["value_numeric"] != 0 else ev["value"]

                if key == "estimated_speed_mph":
                    input_dict["vx_initial"] = float(val) * 1.46667  # mph -> fps
                elif key == "estimated_speed_fps":
                    input_dict["vx_initial"] = float(val)
                elif key in ("weight", "wb", "lcgf", "lcgr", "width", "length",
                             "hcg", "track", "izz", "A", "B", "k", "L", "c",
                             "tire_d", "tire_w", "f_hang", "r_hang"):
                    input_dict[key] = float(val)
                elif key in ("fwd", "rwd", "awd"):
                    input_dict[key] = int(float(val))
                elif key == "head_angle":
                    input_dict["head_angle"] = float(val)
                elif key == "init_x_pos":
                    input_dict["init_x_pos"] = float(val)
                elif key == "init_y_pos":
                    input_dict["init_y_pos"] = float(val)

            results.append({
                "vehicle_number": veh["vehicle_number"],
                "vehicle_id": veh["vehicle_id"],
                "role": veh["role"],
                "input_dict": input_dict,
                "evidence_count": len(evidence),
                "confidence_avg": (
                    sum(e["confidence"] for e in evidence) / len(evidence)
                    if evidence else 0.0
                ),
            })

        return results

    # ------------------------------------------------------------------
    # Export / Import (.crash file)
    # ------------------------------------------------------------------

    def export(self, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Export the full case graph as a portable dict / .crash file.

        The .crash format is a JSON file containing:
        - case metadata
        - all nodes with labels and properties
        - all edges with types and properties
        - pycrash projection (ready-to-use input dicts)
        """
        # Get all nodes
        nodes_result = self._graph.query(
            """
            MATCH (v:Vehicle)-[:INVOLVED_IN]->(:Case {case_id: $case_id})
            OPTIONAL MATCH (e:Evidence)-[:APPLIES_TO]->(v)
            OPTIONAL MATCH (s:Source)-[:OBSERVED]->(e)
            OPTIONAL MATCH (sc:Scene)-[:APPLIES_TO]->(:Case {case_id: $case_id})
            RETURN collect(DISTINCT v), collect(DISTINCT e),
                   collect(DISTINCT s), collect(DISTINCT sc)
            """,
            params={"case_id": self.case_id},
        )

        vehicles = self.get_vehicles()
        projection = self.project_to_pycrash()
        contradictions = self.find_contradictions()
        gaps = self.find_gaps()

        # Collect all evidence
        all_evidence = []
        for veh in vehicles:
            evidence = self.get_evidence_for_vehicle(veh["vehicle_number"])
            for e in evidence:
                e["vehicle_number"] = veh["vehicle_number"]
                all_evidence.append(e)

        export_data = {
            "format": "pycrash_case",
            "version": "1.0",
            "case_id": self.case_id,
            "title": self.title,
            "vehicles": vehicles,
            "evidence": all_evidence,
            "contradictions": contradictions,
            "gaps": gaps,
            "projection": projection,
        }

        if filepath:
            with open(filepath, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

        return export_data

    @classmethod
    def import_crash_file(cls, filepath: str, store: 'CaseGraphStore') -> 'CaseGraph':
        """Import a .crash file into a new case graph."""
        with open(filepath) as f:
            data = json.load(f)

        case = store.create_case(
            case_id=data["case_id"],
            title=data.get("title", ""),
        )

        # Recreate vehicles
        for veh in data.get("vehicles", []):
            case.add_vehicle(
                vehicle_number=veh["vehicle_number"],
                make=veh.get("make"),
                model=veh.get("model"),
                year=veh.get("year"),
                role=veh.get("role", "unknown"),
            )

        case.add_scene()

        # Recreate evidence
        for ev in data.get("evidence", []):
            case.add_evidence(
                category=ev["category"],
                key=ev["key"],
                value=ev.get("value_numeric", ev["value"]),
                unit=ev.get("unit", ""),
                confidence=ev.get("confidence", 0.5),
                source_type=ev.get("source_type", "analyst"),
                applies_to_vehicle=ev.get("vehicle_number"),
            )

        return case


class CaseGraphStore:
    """Manages crash case graphs in FalkorDB."""

    def __init__(self, host: str = "localhost", port: int = 6379,
                 redis_url: Optional[str] = None):
        """Connect to FalkorDB.

        Args:
            host: FalkorDB/Redis host
            port: FalkorDB/Redis port
            redis_url: Full Redis URL (overrides host/port)
        """
        try:
            from falkordb import FalkorDB
            if redis_url:
                # Parse redis URL
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

    def create_case(self, case_id: str, title: str = "",
                    date_of_loss: str = "") -> CaseGraph:
        """Create a new case graph."""
        if not self._connected:
            raise RuntimeError("Not connected to FalkorDB. Is it running?")

        graph_name = f"case_{case_id.replace('-', '_').replace(' ', '_')}"
        graph = self._db.select_graph(graph_name)

        graph.query(
            """
            CREATE (c:Case {
                case_id: $case_id,
                title: $title,
                date_of_loss: $date_of_loss
            })
            """,
            params={
                "case_id": case_id,
                "title": title,
                "date_of_loss": date_of_loss,
            },
        )

        return CaseGraph(graph, case_id, title)

    def open_case(self, case_id: str) -> CaseGraph:
        """Open an existing case graph."""
        if not self._connected:
            raise RuntimeError("Not connected to FalkorDB.")

        graph_name = f"case_{case_id.replace('-', '_').replace(' ', '_')}"
        graph = self._db.select_graph(graph_name)

        result = graph.query(
            "MATCH (c:Case {case_id: $case_id}) RETURN c.title",
            params={"case_id": case_id},
        )

        title = result.result_set[0][0] if result.result_set else ""
        return CaseGraph(graph, case_id, title)

    def list_cases(self) -> List[str]:
        """List all case graph names."""
        if not self._connected:
            return []
        return [g for g in self._db.list_graphs() if g.startswith("case_")]


# --- In-memory fallback for testing without FalkorDB ---

class InMemoryCaseGraph(CaseGraph):
    """In-memory graph implementation for testing without FalkorDB."""

    def __init__(self, case_id: str, title: str = ""):
        self.case_id = case_id
        self.title = title
        self._vehicles: List[Dict[str, Any]] = []
        self._evidence: List[Dict[str, Any]] = []
        self._sources: List[Dict[str, Any]] = []
        self._edges: List[Dict[str, Any]] = []
        self._scene_id: Optional[str] = None

    def add_vehicle(self, vehicle_number, make=None, model=None,
                    year=None, role="unknown"):
        vehicle_id = f"{self.case_id}_v{vehicle_number}"
        self._vehicles.append({
            "vehicle_id": vehicle_id, "vehicle_number": vehicle_number,
            "year": year or 0, "make": make or "Unknown",
            "model": model or "Unknown", "role": role,
        })
        return vehicle_id

    def add_source(self, source_type, description=""):
        source_id = f"{self.case_id}_src_{uuid.uuid4().hex[:6]}"
        self._sources.append({
            "source_id": source_id, "source_type": source_type,
            "description": description,
        })
        return source_id

    def add_evidence(self, category, key, value, unit="", confidence=0.5,
                     source_type="analyst", source_id=None,
                     applies_to_vehicle=None, applies_to_scene=False):
        evidence_id = f"{self.case_id}_ev_{uuid.uuid4().hex[:6]}"
        self._evidence.append({
            "evidence_id": evidence_id, "category": category,
            "key": key, "value": str(value),
            "value_numeric": float(value) if _is_numeric(value) else 0.0,
            "unit": unit, "confidence": confidence,
            "source_type": source_type,
            "vehicle_number": applies_to_vehicle,
        })
        return evidence_id

    def add_scene(self):
        self._scene_id = f"{self.case_id}_scene"
        return self._scene_id

    def mark_contradiction(self, id1, id2, reason=""):
        self._edges.append({"type": "CONTRADICTS", "from": id1, "to": id2, "reason": reason})

    def mark_supports(self, id1, id2):
        self._edges.append({"type": "SUPPORTS", "from": id1, "to": id2})

    def get_vehicles(self):
        return sorted(self._vehicles, key=lambda v: v["vehicle_number"])

    def get_evidence_for_vehicle(self, vehicle_number):
        return [e for e in self._evidence if e.get("vehicle_number") == vehicle_number]

    def find_contradictions(self):
        # Simple: find same key, different value on same vehicle
        contradictions = []
        by_vehicle: Dict[int, List[Dict]] = {}
        for e in self._evidence:
            vn = e.get("vehicle_number")
            if vn is not None:
                by_vehicle.setdefault(vn, []).append(e)

        for vn, evs in by_vehicle.items():
            by_key: Dict[str, List[Dict]] = {}
            for e in evs:
                by_key.setdefault(e["key"], []).append(e)
            for key, group in by_key.items():
                if len(group) > 1:
                    for i in range(len(group)):
                        for j in range(i + 1, len(group)):
                            if group[i]["value"] != group[j]["value"]:
                                contradictions.append({
                                    "key": key,
                                    "evidence_1": group[i],
                                    "evidence_2": group[j],
                                })
        return contradictions

    def find_gaps(self):
        required = ["weight", "wb", "lcgf", "lcgr", "width", "length",
                     "hcg", "track", "izz", "fwd", "rwd", "awd"]
        gaps = []
        for veh in self._vehicles:
            evidence = self.get_evidence_for_vehicle(veh["vehicle_number"])
            known = {e["key"] for e in evidence if e["category"] == "vehicle_spec"}
            missing = [p for p in required if p not in known]
            speed_ev = [e for e in evidence if e["category"] == "speed"]
            if not speed_ev:
                missing.append("estimated_speed")
            if missing:
                gaps.append({
                    "vehicle_id": veh["vehicle_id"],
                    "make": veh["make"], "model": veh["model"],
                    "missing": missing,
                })
        return gaps

    def export(self, filepath=None):
        projection = self.project_to_pycrash()
        data = {
            "format": "pycrash_case",
            "version": "1.0",
            "case_id": self.case_id,
            "title": self.title,
            "vehicles": self.get_vehicles(),
            "evidence": self._evidence,
            "contradictions": self.find_contradictions(),
            "gaps": self.find_gaps(),
            "projection": projection,
        }
        if filepath:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)
        return data


class InMemoryCaseStore:
    """In-memory store for testing without FalkorDB."""

    def __init__(self):
        self._cases: Dict[str, InMemoryCaseGraph] = {}
        self._connected = True

    @property
    def connected(self):
        return True

    def create_case(self, case_id, title="", date_of_loss=""):
        case = InMemoryCaseGraph(case_id, title)
        self._cases[case_id] = case
        return case

    def open_case(self, case_id):
        return self._cases[case_id]

    def list_cases(self):
        return list(self._cases.keys())


def get_store(redis_url: Optional[str] = None) -> CaseGraphStore | InMemoryCaseStore:
    """Get graph store, falling back to in-memory if FalkorDB unavailable."""
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

    return InMemoryCaseStore()


def _is_numeric(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
