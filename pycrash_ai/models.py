"""Pydantic models for API request/response validation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------

class VehicleInput(BaseModel):
    """Vehicle properties matching pycrash Vehicle input_dict."""
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    weight: float = Field(..., gt=0, description="Vehicle weight in lb")
    vin: Optional[str] = None
    brake: float = Field(0, ge=0, le=1)
    steer_ratio: float = Field(16, gt=0)
    init_x_pos: float = 0
    init_y_pos: float = 0
    head_angle: float = 0
    width: float = Field(..., gt=0, description="Vehicle width in ft")
    length: float = Field(..., gt=0, description="Vehicle length in ft")
    hcg: float = Field(..., gt=0, description="CG height in ft")
    lcgf: float = Field(..., gt=0, description="CG to front axle in ft")
    lcgr: float = Field(..., gt=0, description="CG to rear axle in ft")
    wb: float = Field(..., gt=0, description="Wheelbase in ft")
    track: float = Field(..., gt=0, description="Track width in ft")
    f_hang: float = Field(..., gt=0, description="Front overhang in ft")
    r_hang: float = Field(..., gt=0, description="Rear overhang in ft")
    tire_d: float = Field(2.2, gt=0)
    tire_w: float = Field(0.7, gt=0)
    izz: float = Field(..., gt=0, description="Yaw moment of inertia lb-ft-s^2")
    fwd: int = Field(1, ge=0, le=1)
    rwd: int = Field(0, ge=0, le=1)
    awd: int = Field(0, ge=0, le=1)
    A: float = Field(0, description="Stiffness A coefficient")
    B: float = Field(0, description="Stiffness B coefficient")
    k: float = Field(0, description="Effective stiffness lb/ft")
    L: float = Field(0, description="Crush width in")
    c: float = Field(0, description="Crush depth in")
    vx_initial: float = Field(0, description="Initial forward velocity ft/s")
    vy_initial: float = Field(0, description="Initial lateral velocity ft/s")
    omega_z: float = Field(0, description="Initial yaw rate rad/s")
    striking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class SimulationRequest(BaseModel):
    """Request to run a crash simulation."""
    vehicles: List[VehicleInput] = Field(..., min_length=2, max_length=2)
    model_type: str = Field("sdof", pattern="^(sdof|impc|sideswipe)$")
    cor: float = Field(0.15, ge=0, le=1, description="Coefficient of restitution")
    k: Optional[float] = Field(None, description="Override mutual stiffness lb/ft")
    tstop: float = Field(0.5, gt=0, le=5, description="Simulation stop time (s)")
    dt_motion: float = Field(0.01, gt=0, le=0.1)
    mu_max: float = Field(0.8, gt=0, le=1.5)
    alpha_max: float = Field(0.174533, gt=0)


class SimulationStatus(BaseModel):
    """Simulation job status."""
    job_id: str
    status: str  # queued, running, complete, failed
    progress: float = 0.0
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SDOFRequest(BaseModel):
    """Simplified SDOF-only simulation request."""
    w1: float = Field(..., gt=0, description="Vehicle 1 weight (lb)")
    w2: float = Field(..., gt=0, description="Vehicle 2 weight (lb)")
    v1: float = Field(..., ge=0, description="Vehicle 1 speed (mph)")
    v2: float = Field(0, ge=0, description="Vehicle 2 speed (mph)")
    cor: float = Field(0.15, ge=0, le=1)
    k: float = Field(50000, gt=0, description="Mutual stiffness (lb/ft)")
    tstop: float = Field(0.5, gt=0, le=5)
    v1_brake: float = Field(0, ge=0, le=1)
    v2_brake: float = Field(0, ge=0, le=1)


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

class MonteCarloVariation(BaseModel):
    """Parameter variation for Monte Carlo analysis."""
    parameter: str
    min_value: float
    max_value: float
    distribution: str = Field("uniform", pattern="^(uniform|normal|triangular)$")


class MonteCarloRequest(BaseModel):
    """Monte Carlo simulation request."""
    base_config: SDOFRequest
    variations: List[MonteCarloVariation]
    n_runs: int = Field(1000, ge=10, le=50000)


class MonteCarloStatus(BaseModel):
    """Monte Carlo job status."""
    job_id: str
    status: str
    progress: float = 0.0
    completed_runs: int = 0
    total_runs: int = 0
    results: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class ExtractionRequest(BaseModel):
    """Request to extract crash data from text."""
    text: str = Field(..., min_length=10, description="Police report or crash description")
    extract_vehicles: bool = True
    extract_crash_params: bool = True
    extract_scene: bool = True


class ExtractedVehicle(BaseModel):
    """Vehicle data extracted from text."""
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    estimated_speed_mph: Optional[float] = None
    travel_direction: Optional[str] = None
    role: Optional[str] = None  # striking, struck
    damage_description: Optional[str] = None
    confidence: float = Field(0.0, ge=0, le=1)


class ExtractedScene(BaseModel):
    """Scene data extracted from text."""
    road_surface: Optional[str] = None
    weather: Optional[str] = None
    skid_marks_ft: Optional[float] = None
    road_grade_pct: Optional[float] = None
    speed_limit_mph: Optional[float] = None
    intersection: bool = False
    confidence: float = 0.0


class ExtractionResponse(BaseModel):
    """Response from extraction agent."""
    vehicles: List[ExtractedVehicle] = []
    crash_type: Optional[str] = None  # rear-end, intersection, sideswipe, head-on
    scene: Optional[ExtractedScene] = None
    suggested_model: Optional[str] = None  # sdof, impc, sideswipe
    raw_extraction: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class ReportRequest(BaseModel):
    """Request to generate a report."""
    simulation_job_id: str
    montecarlo_job_id: Optional[str] = None
    case_number: Optional[str] = None
    case_title: Optional[str] = None
    analyst_name: Optional[str] = None
    date_of_loss: Optional[str] = None
    narrative_prompt: Optional[str] = None


class ReportResponse(BaseModel):
    """Generated report info."""
    report_id: str
    pdf_url: str
    html_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Vehicle Database
# ---------------------------------------------------------------------------

class IMPCVehicleInput(BaseModel):
    """Simplified vehicle input for IMPC momentum calculation."""
    weight: float = Field(..., gt=0, description="Vehicle weight (lb)")
    speed_mph: float = Field(..., ge=0, description="Pre-impact speed (mph)")
    heading_deg: float = Field(0, description="Heading angle (degrees, 0=east, CCW positive)")
    lateral_speed_mph: float = Field(0, description="Lateral speed (mph)")
    yaw_rate_deg_s: float = Field(0, description="Yaw rate (deg/s)")
    izz: float = Field(0, gt=0, description="Yaw moment of inertia (lb-ft-s^2)")
    impact_dx_ft: float = Field(0, description="Impact point x offset from CG in vehicle frame (ft)")
    impact_dy_ft: float = Field(0, description="Impact point y offset from CG in vehicle frame (ft)")


class IMPCRequest(BaseModel):
    """Impulse-momentum planar collision request.

    This is a simplified wrapper around the Carpenter & Welcher IMPC model.
    It performs the momentum-based collision calculation directly without
    requiring the full Impact simulation infrastructure (no tire model,
    no trajectory integration, no impact detection geometry).

    Limitations:
    - Single instantaneous collision only (no multi-impact sequences)
    - No pre/post-impact vehicle trajectory simulation
    - Impact point offsets from CG must be provided directly
    - No impact plane angle auto-detection; uses impact_plane_angle_deg
    """
    vehicle1: IMPCVehicleInput = Field(..., description="Striking vehicle")
    vehicle2: IMPCVehicleInput = Field(..., description="Struck vehicle")
    impact_plane_angle_deg: float = Field(0, description="Impact plane angle relative to vehicle 1 heading (degrees)")
    cor: float = Field(0.15, ge=0, le=1, description="Coefficient of restitution")
    vehicle_mu: float = Field(0.3, ge=0, le=1.5, description="Inter-vehicle friction coefficient")


class SideswipeVehicleInput(BaseModel):
    """Simplified vehicle input for sideswipe calculation."""
    weight: float = Field(..., gt=0, description="Vehicle weight (lb)")
    speed_mph: float = Field(..., ge=0, description="Pre-impact speed (mph)")
    heading_deg: float = Field(0, description="Heading angle (degrees)")
    lateral_speed_mph: float = Field(0, description="Lateral speed (mph)")


class SideswipeRequest(BaseModel):
    """Sideswipe collision request.

    This is a simplified sideswipe model that calculates forces and
    impulse from continuous contact between two vehicles traveling
    in similar directions with lateral overlap.

    The model applies normal force from crush depth * mutual stiffness
    and friction force from relative sliding velocity.

    Limitations:
    - Simplified 1D overlap model (no full 2D geometry)
    - No tire forces or vehicle dynamics during contact
    - Assumes parallel or near-parallel travel directions
    - Contact duration and overlap depth are user-specified
    """
    vehicle1: SideswipeVehicleInput = Field(..., description="Vehicle 1")
    vehicle2: SideswipeVehicleInput = Field(..., description="Vehicle 2")
    overlap_ft: float = Field(0.5, gt=0, description="Lateral overlap / crush depth (ft)")
    contact_length_ft: float = Field(5.0, gt=0, description="Longitudinal contact length (ft)")
    kmutual: float = Field(30000, gt=0, description="Mutual stiffness (lb/ft)")
    vehicle_mu: float = Field(0.5, ge=0, le=1.5, description="Inter-vehicle friction coefficient")


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

class VehiclePosition(BaseModel):
    """Vehicle position for crash scene visualization."""
    x: float = 0  # center position X (ft)
    y: float = 0  # center position Y (ft)
    heading: float = 0  # heading angle (degrees, 0=east, 90=north)
    length: float = 15  # vehicle length (ft)
    width: float = 6  # vehicle width (ft)
    label: str = "Vehicle"
    color: str = "blue"


class VisualizationRequest(BaseModel):
    """Request to generate a 2D crash scene diagram."""
    vehicles: list[VehiclePosition]
    impact_point: Optional[Dict[str, float]] = None  # {x, y}
    title: str = "Crash Scene"
    show_grid: bool = True


class VehicleLookupResponse(BaseModel):
    """Vehicle specs from database."""
    year: int
    make: str
    model: str
    weight: float
    wb: float
    lcgf: float
    lcgr: float
    width: float
    length: float
    hcg: float
    track: float
    f_hang: float
    r_hang: float
    izz: float
    fwd: int
    rwd: int
    awd: int
    A: float = 0
    B: float = 0
    k: float = 0
    source: str = "estimated"
