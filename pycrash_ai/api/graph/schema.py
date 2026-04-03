"""6-layer crash reconstruction hypergraph schema.

A crash case is not a flat list of facts — it's a multi-dimensional
relational structure. This schema models six interconnected graph layers,
each capturing a different dimension of crash reconstruction.

LAYER 1 — ENTITY (who/what)
    Nodes: Case, Vehicle, Driver, Pedestrian, Object
    What it does: Identifies every actor and object involved.
    Cross-links: Vehicles have Positions (spatial), Events (temporal),
                 Factors (causal), Forces (physical).

LAYER 2 — TEMPORAL (when / sequence)
    Nodes: Event, Phase
    What it does: Reconstructs the timeline. Pre-crash → point of no return
                  → evasive action → first contact → max engagement →
                  separation → rest. Causal chains flow through time.
    Cross-links: Events reference Positions (spatial), involve Entities,
                 are caused by Factors (causal).

LAYER 3 — SPATIAL (where / geometry)
    Nodes: Position, Trajectory, ImpactPoint, Lane, Intersection
    What it does: Models physical space — vehicle trajectories, impact
                  geometry, road layout, rest positions. This is what
                  pycrash actually simulates.
    Cross-links: Positions have timestamps (temporal), belong to
                 Vehicles (entity), map to sim coordinates.

LAYER 4 — EVIDENCE (what we know / confidence)
    Nodes: Evidence, Source
    What it does: Tracks every piece of information with provenance
                  and confidence. Detects contradictions, identifies gaps.
                  THIS IS THE LAYER AGENTS USE TO REASON.
    Cross-links: Evidence supports/contradicts other Evidence, applies
                 to any node in any other layer.

LAYER 5 — CAUSAL (why / contributing factors)
    Nodes: Factor, Contribution
    What it does: Models the causal chain. Distraction → late perception
                  → delayed braking → excessive speed at impact. Enables
                  "what if" counterfactual analysis.
    Cross-links: Factors cause Events (temporal), involve Entities,
                 are supported by Evidence.

LAYER 6 — PHYSICAL (forces / energy / mechanics)
    Nodes: Force, Crush, Energy, DeltaV
    What it does: Captures the physics. Impact forces, crush profiles,
                  energy dissipation, delta-V vectors. This is where
                  pycrash simulation results live.
    Cross-links: Forces occur at ImpactPoints (spatial), during Events
                 (temporal), applied to Vehicles (entity).

CROSS-LAYER EDGES:
    The hypergraph connects layers through typed relationships:

    Entity ↔ Temporal:   PARTICIPATED_IN (Vehicle → Event)
    Entity ↔ Spatial:    AT_POSITION (Vehicle → Position)
    Entity ↔ Physical:   EXPERIENCED (Vehicle → DeltaV/Force)
    Temporal ↔ Spatial:  OCCURRED_AT (Event → Position)
    Temporal ↔ Causal:   CAUSED_BY (Event → Factor)
    Temporal ↔ Physical: PRODUCED (Event → Force)
    Spatial ↔ Physical:  APPLIED_AT (Force → ImpactPoint)
    Evidence → *:        DESCRIBES (Evidence → any node in any layer)
    Causal ↔ Evidence:   SUPPORTED_BY (Factor → Evidence)

HYPERGRAPH QUERIES (what agents can ask):
    - "What evidence supports the causal chain leading to max delta-V?"
      (Evidence → Causal → Temporal → Physical)
    - "Where was Vehicle 1 when the perception-reaction phase began?"
      (Entity → Temporal → Spatial)
    - "What contradicting evidence exists about speed at impact?"
      (Evidence layer self-query)
    - "What factors would have changed the outcome?"
      (Causal → counterfactual simulation → Physical)
    - "Show me the timeline from first evidence of distraction to rest"
      (Causal → Temporal, with Evidence support at each step)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ===================================================================
# LAYER ENUM — which layer a node belongs to
# ===================================================================

class GraphLayer(str, Enum):
    ENTITY = "entity"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    EVIDENCE = "evidence"
    CAUSAL = "causal"
    PHYSICAL = "physical"


# ===================================================================
# NODE LABELS — organized by layer
# ===================================================================

class NodeLabel(str, Enum):
    # --- Entity layer ---
    CASE = "Case"
    VEHICLE = "Vehicle"
    DRIVER = "Driver"
    PEDESTRIAN = "Pedestrian"
    OBJECT = "Object"           # guardrail, pole, tree, etc.

    # --- Temporal layer ---
    EVENT = "Event"             # a discrete occurrence in time
    PHASE = "Phase"             # pre-crash, impact, post-crash

    # --- Spatial layer ---
    POSITION = "Position"       # x, y, heading at a moment
    TRAJECTORY = "Trajectory"   # sequence of positions
    IMPACT_POINT = "ImpactPoint"  # where vehicles contacted
    LANE = "Lane"
    INTERSECTION = "Intersection"

    # --- Evidence layer ---
    EVIDENCE = "Evidence"
    SOURCE = "Source"

    # --- Causal layer ---
    FACTOR = "Factor"           # contributing factor (distraction, speed, etc.)
    CONTRIBUTION = "Contribution"  # weighted link: factor → outcome

    # --- Physical layer ---
    FORCE = "Force"             # impact force vector
    CRUSH = "Crush"             # crush profile / depth
    ENERGY = "Energy"           # dissipated energy
    DELTA_V = "DeltaV"          # velocity change vector

    # --- Simulation layer (connects physical back to entity) ---
    SIM_CONFIG = "SimConfig"
    SIM_RESULT = "SimResult"
    GAP = "Gap"


# Map each label to its layer
NODE_LAYER: Dict[NodeLabel, GraphLayer] = {
    NodeLabel.CASE: GraphLayer.ENTITY,
    NodeLabel.VEHICLE: GraphLayer.ENTITY,
    NodeLabel.DRIVER: GraphLayer.ENTITY,
    NodeLabel.PEDESTRIAN: GraphLayer.ENTITY,
    NodeLabel.OBJECT: GraphLayer.ENTITY,
    NodeLabel.EVENT: GraphLayer.TEMPORAL,
    NodeLabel.PHASE: GraphLayer.TEMPORAL,
    NodeLabel.POSITION: GraphLayer.SPATIAL,
    NodeLabel.TRAJECTORY: GraphLayer.SPATIAL,
    NodeLabel.IMPACT_POINT: GraphLayer.SPATIAL,
    NodeLabel.LANE: GraphLayer.SPATIAL,
    NodeLabel.INTERSECTION: GraphLayer.SPATIAL,
    NodeLabel.EVIDENCE: GraphLayer.EVIDENCE,
    NodeLabel.SOURCE: GraphLayer.EVIDENCE,
    NodeLabel.FACTOR: GraphLayer.CAUSAL,
    NodeLabel.CONTRIBUTION: GraphLayer.CAUSAL,
    NodeLabel.FORCE: GraphLayer.PHYSICAL,
    NodeLabel.CRUSH: GraphLayer.PHYSICAL,
    NodeLabel.ENERGY: GraphLayer.PHYSICAL,
    NodeLabel.DELTA_V: GraphLayer.PHYSICAL,
    NodeLabel.SIM_CONFIG: GraphLayer.PHYSICAL,
    NodeLabel.SIM_RESULT: GraphLayer.PHYSICAL,
    NodeLabel.GAP: GraphLayer.EVIDENCE,
}


# ===================================================================
# EDGE TYPES — intra-layer and cross-layer
# ===================================================================

class EdgeType(str, Enum):
    # --- Entity layer (intra) ---
    INVOLVED_IN = "INVOLVED_IN"       # Vehicle/Driver → Case
    DRIVEN_BY = "DRIVEN_BY"           # Vehicle → Driver
    OCCUPIED_BY = "OCCUPIED_BY"       # Vehicle → Pedestrian/Object (struck)

    # --- Temporal layer (intra) ---
    PRECEDED_BY = "PRECEDED_BY"       # Event → Event (ordering)
    FOLLOWED_BY = "FOLLOWED_BY"       # Event → Event
    BELONGS_TO_PHASE = "BELONGS_TO_PHASE"  # Event → Phase
    PHASE_ORDER = "PHASE_ORDER"       # Phase → Phase

    # --- Spatial layer (intra) ---
    CONNECTS = "CONNECTS"             # Lane → Intersection
    ADJACENT_TO = "ADJACENT_TO"       # Lane → Lane
    PART_OF_TRAJECTORY = "PART_OF_TRAJECTORY"  # Position → Trajectory

    # --- Evidence layer (intra) ---
    OBSERVED = "OBSERVED"             # Source → Evidence
    SUPPORTS = "SUPPORTS"             # Evidence → Evidence
    CONTRADICTS = "CONTRADICTS"       # Evidence → Evidence
    INFERRED_FROM = "INFERRED_FROM"   # Evidence → Evidence (calculated)

    # --- Causal layer (intra) ---
    CONTRIBUTED_TO = "CONTRIBUTED_TO"  # Factor → Factor (chain)
    MITIGATED_BY = "MITIGATED_BY"     # Factor → Factor (counterfactual)

    # --- Physical layer (intra) ---
    PRODUCED_BY = "PRODUCED_BY"       # SimResult → SimConfig
    DISSIPATED_AS = "DISSIPATED_AS"   # Energy → Crush

    # === CROSS-LAYER EDGES ===

    # Entity ↔ Temporal
    PARTICIPATED_IN = "PARTICIPATED_IN"   # Vehicle/Driver → Event
    # Entity ↔ Spatial
    AT_POSITION = "AT_POSITION"           # Vehicle → Position
    LOCATED_AT = "LOCATED_AT"             # Object → Position
    # Entity ↔ Physical
    EXPERIENCED = "EXPERIENCED"           # Vehicle → DeltaV/Force/Crush
    # Temporal ↔ Spatial
    OCCURRED_AT = "OCCURRED_AT"           # Event → Position/ImpactPoint
    # Temporal ↔ Causal
    CAUSED_BY = "CAUSED_BY"               # Event → Factor
    RESULTED_IN = "RESULTED_IN"           # Factor → Event
    # Temporal ↔ Physical
    PRODUCED = "PRODUCED"                 # Event → Force/Energy/DeltaV
    # Spatial ↔ Physical
    APPLIED_AT = "APPLIED_AT"             # Force → ImpactPoint
    CRUSH_AT = "CRUSH_AT"                 # Crush → ImpactPoint/Position

    # Evidence → anything (the evidence layer reaches into all others)
    DESCRIBES = "DESCRIBES"               # Evidence → any node
    APPLIES_TO = "APPLIES_TO"             # Evidence/Source → target entity
    PROJECTED_TO = "PROJECTED_TO"         # Evidence → SimConfig
    NEEDS = "NEEDS"                       # Gap → Vehicle/Scene

    # Causal ↔ Evidence
    SUPPORTED_BY = "SUPPORTED_BY"         # Factor → Evidence


# Which edges are cross-layer
CROSS_LAYER_EDGES = {
    EdgeType.PARTICIPATED_IN,
    EdgeType.AT_POSITION,
    EdgeType.LOCATED_AT,
    EdgeType.EXPERIENCED,
    EdgeType.OCCURRED_AT,
    EdgeType.CAUSED_BY,
    EdgeType.RESULTED_IN,
    EdgeType.PRODUCED,
    EdgeType.APPLIED_AT,
    EdgeType.CRUSH_AT,
    EdgeType.DESCRIBES,
    EdgeType.APPLIES_TO,
    EdgeType.PROJECTED_TO,
    EdgeType.SUPPORTED_BY,
}


# ===================================================================
# EVIDENCE & SOURCE ENUMS
# ===================================================================

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
    TRAJECTORY = "trajectory"
    CRUSH_PROFILE = "crush_profile"
    INJURY = "injury"
    VISIBILITY = "visibility"


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
    LIDAR = "lidar"
    SURVEY = "survey"
    SIMULATION = "simulation"


# ===================================================================
# TEMPORAL — pre-defined crash phases and event types
# ===================================================================

class CrashPhase(str, Enum):
    """Standard phases of a crash event."""
    NORMAL_DRIVING = "normal_driving"
    PERCEPTION = "perception"           # hazard first perceivable
    REACTION = "reaction"               # driver begins response
    EVASIVE_ACTION = "evasive_action"   # braking/steering
    PRE_IMPACT = "pre_impact"           # committed to collision
    FIRST_CONTACT = "first_contact"     # impact begins
    MAX_ENGAGEMENT = "max_engagement"   # peak crush
    SEPARATION = "separation"           # vehicles separate
    POST_IMPACT = "post_impact"         # motion after separation
    REST = "rest"                       # final positions


class EventType(str, Enum):
    """Types of discrete events in a crash timeline."""
    PERCEPTION_POINT = "perception_point"
    BRAKE_APPLICATION = "brake_application"
    STEER_INPUT = "steer_input"
    LANE_DEPARTURE = "lane_departure"
    FIRST_CONTACT = "first_contact"
    MAX_ENGAGEMENT = "max_engagement"
    SEPARATION = "separation"
    SECONDARY_CONTACT = "secondary_contact"
    ROLLOVER_INITIATION = "rollover_initiation"
    VEHICLE_REST = "vehicle_rest"
    AIRBAG_DEPLOYMENT = "airbag_deployment"


# ===================================================================
# CAUSAL — standard contributing factors
# ===================================================================

class ContributingFactor(str, Enum):
    """Standard contributing factors in crash causation."""
    EXCESSIVE_SPEED = "excessive_speed"
    DISTRACTION = "distraction"
    IMPAIRMENT_ALCOHOL = "impairment_alcohol"
    IMPAIRMENT_DRUG = "impairment_drug"
    FATIGUE = "fatigue"
    FOLLOWING_DISTANCE = "following_distance"
    FAILURE_TO_YIELD = "failure_to_yield"
    RED_LIGHT_VIOLATION = "red_light_violation"
    STOP_SIGN_VIOLATION = "stop_sign_violation"
    IMPROPER_LANE_CHANGE = "improper_lane_change"
    WRONG_WAY = "wrong_way"
    ROAD_CONDITION = "road_condition"
    WEATHER_CONDITION = "weather_condition"
    VEHICLE_DEFECT = "vehicle_defect"
    OBSCURED_VISION = "obscured_vision"
    SUN_GLARE = "sun_glare"
    PEDESTRIAN_ERROR = "pedestrian_error"
    UNKNOWN = "unknown"


# ===================================================================
# DATA CLASSES
# ===================================================================

@dataclass
class NodeData:
    """Data for a graph node."""
    label: NodeLabel
    properties: Dict[str, Any] = field(default_factory=dict)
    node_id: Optional[str] = None
    layer: Optional[GraphLayer] = None

    def __post_init__(self):
        if self.layer is None:
            self.layer = NODE_LAYER.get(self.label)


@dataclass
class EdgeData:
    """Data for a graph edge."""
    edge_type: EdgeType
    from_id: str
    to_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_cross_layer(self) -> bool:
        return self.edge_type in CROSS_LAYER_EDGES


# ===================================================================
# REQUIRED PARAMETERS — what pycrash needs per entity
# ===================================================================

REQUIRED_VEHICLE_PARAMS = [
    "weight", "wb", "lcgf", "lcgr", "width", "length",
    "hcg", "track", "izz", "fwd", "rwd", "awd",
]

REQUIRED_SCENE_PARAMS = [
    "surface",  # road surface type
]

RECOMMENDED_VEHICLE_PARAMS = [
    "A", "B", "k", "L", "c",  # stiffness
    "tire_d", "tire_w", "f_hang", "r_hang",  # geometry
    "steer_ratio",
]

# ===================================================================
# PYCRASH COORDINATE MAPPING
# ===================================================================

# Map evidence keys to pycrash Vehicle input dict keys
EVIDENCE_TO_PYCRASH = {
    "estimated_speed_mph": ("vx_initial", lambda v: float(v) * 1.46667),
    "estimated_speed_fps": ("vx_initial", lambda v: float(v)),
    "weight": ("weight", float),
    "wb": ("wb", float),
    "lcgf": ("lcgf", float),
    "lcgr": ("lcgr", float),
    "width": ("width", float),
    "length": ("length", float),
    "hcg": ("hcg", float),
    "track": ("track", float),
    "izz": ("izz", float),
    "A": ("A", float),
    "B": ("B", float),
    "k": ("k", float),
    "L": ("L", float),
    "c": ("c", float),
    "tire_d": ("tire_d", float),
    "tire_w": ("tire_w", float),
    "f_hang": ("f_hang", float),
    "r_hang": ("r_hang", float),
    "steer_ratio": ("steer_ratio", float),
    "fwd": ("fwd", lambda v: int(float(v))),
    "rwd": ("rwd", lambda v: int(float(v))),
    "awd": ("awd", lambda v: int(float(v))),
    "head_angle": ("head_angle", float),
    "init_x_pos": ("init_x_pos", float),
    "init_y_pos": ("init_y_pos", float),
}
