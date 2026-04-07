"""
OpenSim musculoskeletal modeling integration for pycrash crash reconstruction.

Bridges the gap between vehicle-level reconstruction (pycrash/BeamNG) and
occupant-level biomechanical injury analysis (OpenSim).

Pipeline:
  pycrash (delta-V, acceleration pulse) ->
  crash pulse generation ->
  OpenSim external forces ->
  forward dynamics / inverse dynamics ->
  joint forces, muscle loads, injury risk metrics

Requires: opensim (pip install opensim)
          OpenSim 4.x+ (https://opensim.stanford.edu)
"""

from .crash_pulse import CrashPulseGenerator
from .occupant_model import OccupantModel
from .injury_risk import InjuryRiskAssessment

__all__ = [
    "CrashPulseGenerator",
    "OccupantModel",
    "InjuryRiskAssessment",
]
