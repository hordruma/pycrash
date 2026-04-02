"""Crash case graph schema.

The graph is the evidence space for a crash reconstruction case.
Every piece of information — from a police report, witness statement,
EDR download, photo, or analyst input — becomes a node with provenance.

Agents traverse this graph to:
1. Understand what's known vs unknown
2. Detect contradictions between sources
3. Identify what's needed before simulation can run
4. Project evidence into pycrash simulation parameters

NODE TYPES (Labels):
    Case            - Root node for a crash case
    Vehicle         - A vehicle involved (year, make, model, weight, ...)
    Driver          - Driver of a vehicle
    Occupant        - Any occupant
    Evidence        - A piece of evidence (speed, skid marks, damage, ...)
    Source          - Where evidence came from (police report, witness, EDR, photo, ...)
    Scene           - Road, weather, environment conditions
    SimConfig       - A simulation configuration projected from evidence
    SimResult       - Results from running a simulation
    Gap             - Identified missing information needed for reconstruction

EDGE TYPES (Relationships):
    INVOLVED_IN     - Vehicle/Driver -> Case
    DRIVEN_BY       - Vehicle -> Driver
    OBSERVED         - Source -> Evidence (this source produced this evidence)
    APPLIES_TO      - Evidence -> Vehicle/Scene (what does this evidence describe)
    SUPPORTS        - Evidence -> Evidence (corroborates)
    CONTRADICTS     - Evidence -> Evidence (conflicts with)
    INFERRED_FROM   - Evidence -> Evidence (derived/calculated from)
    PROJECTED_TO    - Evidence -> SimConfig (evidence mapped to sim parameter)
    PRODUCED_BY     - SimResult -> SimConfig
    NEEDS           - Gap -> Vehicle/Scene (what's missing for this entity)

EVIDENCE PROPERTIES:
    Every Evidence node carries:
    - value: the actual data (speed=35, surface="dry_asphalt", etc.)
    - unit: measurement unit
    - confidence: 0.0-1.0
    - source_type: "police_report", "witness", "edr", "photo", "analyst", "calculated"
    - category: "speed", "position", "damage", "road", "weather", "vehicle_spec", etc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeLabel(str, Enum):
    CASE = "Case"
    VEHICLE = "Vehicle"
    DRIVER = "Driver"
    OCCUPANT = "Occupant"
    EVIDENCE = "Evidence"
    SOURCE = "Source"
    SCENE = "Scene"
    SIM_CONFIG = "SimConfig"
    SIM_RESULT = "SimResult"
    GAP = "Gap"


class EdgeType(str, Enum):
    INVOLVED_IN = "INVOLVED_IN"
    DRIVEN_BY = "DRIVEN_BY"
    OBSERVED = "OBSERVED"
    APPLIES_TO = "APPLIES_TO"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INFERRED_FROM = "INFERRED_FROM"
    PROJECTED_TO = "PROJECTED_TO"
    PRODUCED_BY = "PRODUCED_BY"
    NEEDS = "NEEDS"


class EvidenceCategory(str, Enum):
    SPEED = "speed"
    POSITION = "position"
    HEADING = "heading"
    DAMAGE = "damage"
    SKID_MARKS = "skid_marks"
    ROAD_SURFACE = "road_surface"
    WEATHER = "weather"
    VEHICLE_SPEC = "vehicle_spec"
    STIFFNESS = "stiffness"
    DRIVER_ACTION = "driver_action"
    IMPACT_CONFIG = "impact_config"
    TIMING = "timing"
    FRICTION = "friction"


class SourceType(str, Enum):
    POLICE_REPORT = "police_report"
    WITNESS = "witness"
    EDR = "edr"
    PHOTO = "photo"
    VIDEO = "video"
    ANALYST = "analyst"
    CALCULATED = "calculated"
    DATABASE = "database"
    NHTSA = "nhtsa"


@dataclass
class NodeData:
    """Data for a graph node."""
    label: NodeLabel
    properties: Dict[str, Any] = field(default_factory=dict)
    node_id: Optional[str] = None  # auto-generated if None


@dataclass
class EdgeData:
    """Data for a graph edge."""
    edge_type: EdgeType
    from_id: str
    to_id: str
    properties: Dict[str, Any] = field(default_factory=dict)


# --- Cypher query templates ---

CREATE_CASE = """
CREATE (c:Case {
    case_id: $case_id,
    title: $title,
    date_of_loss: $date_of_loss,
    created_at: timestamp()
})
RETURN c
"""

CREATE_VEHICLE = """
MATCH (c:Case {case_id: $case_id})
CREATE (v:Vehicle {
    vehicle_id: $vehicle_id,
    vehicle_number: $vehicle_number,
    year: $year,
    make: $make,
    model: $model,
    role: $role
})
CREATE (v)-[:INVOLVED_IN]->(c)
RETURN v
"""

CREATE_SOURCE = """
MATCH (c:Case {case_id: $case_id})
CREATE (s:Source {
    source_id: $source_id,
    source_type: $source_type,
    description: $description,
    ingested_at: timestamp()
})
CREATE (s)-[:APPLIES_TO]->(c)
RETURN s
"""

CREATE_EVIDENCE = """
CREATE (e:Evidence {
    evidence_id: $evidence_id,
    category: $category,
    key: $key,
    value: $value,
    unit: $unit,
    confidence: $confidence,
    source_type: $source_type
})
RETURN e
"""

LINK_EVIDENCE_TO_SOURCE = """
MATCH (s:Source {source_id: $source_id})
MATCH (e:Evidence {evidence_id: $evidence_id})
CREATE (s)-[:OBSERVED]->(e)
"""

LINK_EVIDENCE_TO_ENTITY = """
MATCH (e:Evidence {evidence_id: $evidence_id})
MATCH (target {$target_label_field: $target_id})
CREATE (e)-[:APPLIES_TO]->(target)
"""

CREATE_SCENE = """
MATCH (c:Case {case_id: $case_id})
CREATE (s:Scene {
    scene_id: $scene_id
})
CREATE (s)-[:APPLIES_TO]->(c)
RETURN s
"""

# Evidence conflict detection
FIND_CONTRADICTIONS = """
MATCH (e1:Evidence)-[:APPLIES_TO]->(target)<-[:APPLIES_TO]-(e2:Evidence)
WHERE e1.category = e2.category
  AND e1.key = e2.key
  AND e1.evidence_id <> e2.evidence_id
  AND e1.value <> e2.value
RETURN e1, e2, target
"""

# Find what's needed for simulation
FIND_GAPS = """
MATCH (v:Vehicle)-[:INVOLVED_IN]->(c:Case {case_id: $case_id})
OPTIONAL MATCH (e:Evidence {category: 'vehicle_spec'})-[:APPLIES_TO]->(v)
WITH v, collect(e.key) as known_specs
WITH v, known_specs,
     [x IN ['weight','wb','lcgf','lcgr','width','length','hcg','track','izz']
      WHERE NOT x IN known_specs] as missing
WHERE size(missing) > 0
RETURN v.vehicle_id as vehicle_id, v.make as make, v.model as model, missing
"""

# Project evidence to simulation config
PROJECT_TO_SIM = """
MATCH (v:Vehicle)-[:INVOLVED_IN]->(c:Case {case_id: $case_id})
OPTIONAL MATCH (e:Evidence)-[:APPLIES_TO]->(v)
WITH v, collect({key: e.key, value: e.value, confidence: e.confidence, category: e.category}) as evidence
RETURN v.vehicle_id as vehicle_id, v.vehicle_number as vehicle_number,
       v.year as year, v.make as make, v.model as model, v.role as role,
       evidence
ORDER BY v.vehicle_number
"""

# Export full case graph
EXPORT_CASE = """
MATCH (n)-[r]->(m)
WHERE (n:Case {case_id: $case_id}) OR
      (n)-[:INVOLVED_IN|APPLIES_TO*1..3]->(:Case {case_id: $case_id}) OR
      (:Case {case_id: $case_id})<-[:INVOLVED_IN|APPLIES_TO*1..3]-(n)
RETURN n, r, m
"""
