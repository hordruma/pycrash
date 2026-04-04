"""
BeamNG.drive / BeamNG.tech integration for pycrash crash reconstruction.

This module bridges pycrash's analytical 2D crash reconstruction models
with BeamNG.tech's 3D soft-body physics simulation for:
  - 3D visualization of reconstructed crashes
  - Validation of BeamNG against pycrash's peer-reviewed models
  - Stiffness calibration of BeamNG vehicles against NHTSA data
  - Automated test matrix sweeps for systematic validation
  - Extraction of BeamNG telemetry into pycrash-compatible DataFrames

Requires: beamngpy (pip install beamngpy)
          BeamNG.tech license (https://beamng.tech)
"""

from .vehicle_converter import VehicleConverter
from .scenario_builder import ScenarioBuilder
from .telemetry import TelemetryExtractor
from .validation import ValidationComparator
from .crash_test_validation import (
    NHTSAValidationSuite,
    CrashTestCase,
    AcceptanceCriteria,
)
from .stiffness_calibration import StiffnessCalibrator
from .test_matrix import TestMatrixRunner, standard_matrix, quick_matrix

__all__ = [
    "VehicleConverter",
    "ScenarioBuilder",
    "TelemetryExtractor",
    "ValidationComparator",
    "NHTSAValidationSuite",
    "CrashTestCase",
    "AcceptanceCriteria",
    "StiffnessCalibrator",
    "TestMatrixRunner",
    "standard_matrix",
    "quick_matrix",
]
