"""
BeamNG.drive / BeamNG.tech integration for pycrash crash reconstruction.

This module bridges pycrash's analytical 2D crash reconstruction models
with BeamNG.tech's 3D soft-body physics simulation for:
  - 3D visualization of reconstructed crashes
  - Validation of analytical results against soft-body simulation
  - Extraction of BeamNG telemetry into pycrash-compatible DataFrames

Requires: beamngpy (pip install beamngpy)
          BeamNG.tech license (https://beamng.tech)
"""

from .vehicle_converter import VehicleConverter
from .scenario_builder import ScenarioBuilder
from .telemetry import TelemetryExtractor
from .validation import ValidationComparator

__all__ = [
    "VehicleConverter",
    "ScenarioBuilder",
    "TelemetryExtractor",
    "ValidationComparator",
]
