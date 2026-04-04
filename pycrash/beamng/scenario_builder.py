"""
Builds BeamNG.tech scenarios from pycrash crash reconstruction data.

Takes pycrash Vehicle objects and reconstruction results (KinematicsTwo, IMPC, SDOF)
and creates runnable BeamNG scenarios with correct initial conditions, vehicle
placement, and pre-impact trajectories.
"""

import json
import os
import numpy as np
from .vehicle_converter import VehicleConverter, FT_TO_M, MPH_TO_MS, DEG_TO_RAD


class ScenarioBuilder:
    """
    Constructs BeamNG.tech scenarios from pycrash crash reconstruction inputs.

    Supports:
    - Two-vehicle impact scenarios (from KinematicsTwo / IMPC)
    - Single-vehicle motion scenarios (from SingleMotion)
    - Pre-impact trajectory replay using driver inputs
    - Post-impact trajectory comparison
    """

    def __init__(self, beamng_home=None, level="smallgrid"):
        """
        Args:
            beamng_home: Path to BeamNG.tech installation. If None, uses
                         BEAMNG_HOME env var or prompts at connection time.
            level: BeamNG map/level to use. 'smallgrid' is a flat open area
                   ideal for reconstruction (no terrain interference).
                   Other options: 'gridmap_v2', 'west_coast_usa', 'italy', etc.
        """
        self.beamng_home = beamng_home or os.environ.get("BEAMNG_HOME")
        self.level = level
        self.converter = VehicleConverter(beamng_home)
        self._vehicles = []
        self._waypoints = {}

    def add_vehicle(self, pycrash_vehicle, beamng_model=None, color="White",
                    origin_offset=(0, 0)):
        """
        Add a pycrash Vehicle to the scenario.

        Args:
            pycrash_vehicle: pycrash Vehicle instance with initial conditions set
            beamng_model: BeamNG model override (e.g., 'etk800', 'vivace')
            color: Vehicle color in BeamNG
            origin_offset: (x_m, y_m) world offset for positioning

        Returns:
            self for method chaining
        """
        config = self.converter.to_beamng_config(
            pycrash_vehicle, beamng_model, color, origin_offset
        )
        self._vehicles.append(config)
        return self

    def add_trajectory_waypoints(self, vehicle_name, motion_df, interval=0.5):
        """
        Extract trajectory waypoints from a pycrash motion DataFrame
        for BeamNG AI path following.

        Args:
            vehicle_name: Name matching a previously added vehicle
            motion_df: pycrash motion DataFrame with columns: t, Dx, Dy, Vr, theta_deg
            interval: Time interval (seconds) between waypoints
        """
        waypoints = []
        dt = motion_df['t'].iloc[1] - motion_df['t'].iloc[0] if len(motion_df) > 1 else 0.01
        step = max(1, int(interval / dt))

        for i in range(0, len(motion_df), step):
            row = motion_df.iloc[i]
            wp = {
                'time': float(row['t']),
                'pos': (
                    float(row['Dx']) * FT_TO_M,
                    float(row['Dy']) * FT_TO_M,
                    0.0
                ),
                'speed': float(row['Vr']) * MPH_TO_MS if 'Vr' in row else 0.0,
            }
            waypoints.append(wp)

        self._waypoints[vehicle_name] = waypoints
        return self

    def build_scenario_dict(self, name="pycrash_reconstruction"):
        """
        Build a scenario configuration dict (serializable to JSON).

        This dict can be used to:
        1. Create a BeamNG scenario via beamngpy
        2. Save as a prefab for manual loading in BeamNG
        3. Share reconstruction setups between analysts

        Returns:
            dict with full scenario configuration
        """
        scenario = {
            'name': name,
            'level': self.level,
            'vehicles': self._vehicles,
            'waypoints': self._waypoints,
            'metadata': {
                'source': 'pycrash_beamng_integration',
                'vehicle_count': len(self._vehicles),
            }
        }
        return scenario

    def save_scenario(self, filepath, name="pycrash_reconstruction"):
        """Save scenario configuration to a JSON file."""
        scenario = self.build_scenario_dict(name)
        # Convert tuples to lists for JSON serialization
        with open(filepath, 'w') as f:
            json.dump(scenario, f, indent=2, default=_json_serialize)
        return filepath

    def build_beamngpy_scenario(self, name="pycrash_reconstruction"):
        """
        Build and return a beamngpy Scenario object ready to run.

        Requires beamngpy to be installed. This creates actual BeamNG
        Vehicle and Scenario objects with sensors attached.

        Returns:
            (scenario, vehicles_dict): beamngpy Scenario and dict of Vehicle objects

        Raises:
            ImportError: if beamngpy is not installed
        """
        try:
            from beamngpy import BeamNGpy, Scenario, Vehicle
            from beamngpy.sensors import Damage, Electrics, Timer, State
        except ImportError:
            raise ImportError(
                "beamngpy is required for live BeamNG integration. "
                "Install it with: pip install beamngpy\n"
                "You also need BeamNG.tech: https://beamng.tech"
            )

        scenario = Scenario(self.level, name)
        vehicles = {}

        for veh_config in self._vehicles:
            veh = Vehicle(
                veh_config['name'],
                model=veh_config['model'],
                color=veh_config['color'],
            )

            # Attach sensors for crash data extraction
            veh.sensors.attach('damage', Damage())
            veh.sensors.attach('electrics', Electrics())
            veh.sensors.attach('state', State())
            veh.sensors.attach('timer', Timer())

            scenario.add_vehicle(
                veh,
                pos=veh_config['pos'],
                rot_quat=veh_config['rot'],
            )
            vehicles[veh_config['name']] = veh

        return scenario, vehicles

    def run_reconstruction(self, duration=10.0, dt=0.01, record_video=False):
        """
        Connect to BeamNG.tech, load the scenario, set initial velocities,
        and run the simulation for the specified duration.

        This is the main entry point for running a full reconstruction
        in BeamNG from pycrash initial conditions.

        Args:
            duration: Simulation duration in seconds
            dt: Physics step size in seconds (BeamNG default is 0.0005)
            record_video: If True, captures video frames during simulation

        Returns:
            dict with telemetry data per vehicle (DataFrames),
            or None if beamngpy is not available
        """
        try:
            from beamngpy import BeamNGpy
        except ImportError:
            raise ImportError(
                "beamngpy is required. Install with: pip install beamngpy"
            )

        scenario, vehicles = self.build_beamngpy_scenario()

        bng = BeamNGpy('localhost', 64256, home=self.beamng_home)
        try:
            bng.open()
            scenario.make(bng)
            bng.scenario.load(scenario)
            bng.scenario.start()

            # Set initial velocities for each vehicle
            for veh_config in self._vehicles:
                veh = vehicles[veh_config['name']]
                vel = veh_config['velocity']
                # BeamNG API: set velocity in world frame
                bng.vehicles[veh_config['name']].set_velocity(vel[0], vel[1], vel[2])

            # Run simulation and collect telemetry
            from .telemetry import TelemetryExtractor
            extractor = TelemetryExtractor()
            telemetry = extractor.record(bng, vehicles, duration, dt)

            return telemetry

        finally:
            bng.close()

    def from_kinematicstwo(self, kt_result, beamng_models=None, colors=None):
        """
        Populate the scenario from a pycrash KinematicsTwo result.

        Extracts both vehicles' initial conditions and optionally their
        pre-computed trajectories.

        Args:
            kt_result: pycrash KinematicsTwo instance (after simulation)
            beamng_models: dict mapping vehicle name -> BeamNG model name
            colors: dict mapping vehicle name -> color string

        Returns:
            self for method chaining
        """
        beamng_models = beamng_models or {}
        colors = colors or {}

        for veh, suffix in [(kt_result.veh1, '1'), (kt_result.veh2, '2')]:
            self.add_vehicle(
                veh,
                beamng_model=beamng_models.get(veh.name),
                color=colors.get(veh.name, 'White' if suffix == '1' else 'Red'),
            )

        return self


def _json_serialize(obj):
    """JSON serializer for numpy types and tuples."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
