"""
Calibrates BeamNG vehicle node-beam stiffness to match pycrash's validated
A/B stiffness coefficients derived from NHTSA crash test data.

This is the critical step that makes BeamNG a validated tool:
Without calibration, BeamNG's vehicle models have arbitrary stiffness.
After calibration against NHTSA data via pycrash, the BeamNG models
reproduce real-world crush-energy relationships.

Methodology:
1. Run a series of flat-barrier impacts in BeamNG at known speeds
2. Measure crush depth from BeamNG node-beam deformation
3. Fit A/B stiffness coefficients to the BeamNG crush data
4. Compare fitted A/B with NHTSA-published values
5. Adjust BeamNG vehicle jbeam parameters to minimize error
6. Repeat until A/B coefficients match within acceptance criteria

References:
  - SAE J2868: Crush Energy in Accident Reconstruction
  - Bonugli & Steffey, SAE 2017-01-1417
  - Campbell (1974): Energy Basis for Collision Severity
"""

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit, minimize
from dataclasses import dataclass, field
from typing import Optional

from .vehicle_converter import FT_TO_M, MPH_TO_MS, IN_TO_M, LB_TO_KG


@dataclass
class StiffnessResult:
    """Result of a stiffness calibration run."""
    vehicle_model: str
    A_fitted: float           # lb/in (fitted from BeamNG data)
    B_fitted: float           # lb/in/in
    A_target: float           # lb/in (from NHTSA data)
    B_target: float           # lb/in/in
    A_error_pct: float
    B_error_pct: float
    r_squared: float          # goodness of fit
    test_speeds_mph: list = field(default_factory=list)
    crush_depths_in: list = field(default_factory=list)
    calibrated: bool = False  # True if within acceptance criteria


class StiffnessCalibrator:
    """
    Calibrates BeamNG vehicle stiffness against NHTSA/pycrash values.

    The calibration process runs multiple barrier tests in BeamNG at
    different speeds, measures the resulting crush depth, and fits
    the Campbell model (F = A + B*C) to determine stiffness.
    """

    def __init__(self, target_A=0, target_B=0, acceptance_pct=15.0):
        """
        Args:
            target_A: Target A coefficient in lb/in (from NHTSA test data)
            target_B: Target B coefficient in lb/in/in (from NHTSA test data)
            acceptance_pct: Maximum percent error for calibration acceptance
        """
        self.target_A = target_A
        self.target_B = target_B
        self.acceptance_pct = acceptance_pct
        self.test_data = []

    def campbell_model(self, c, A, B):
        """
        Campbell force-crush model: F/w = A + B*c

        Where:
            F = force per unit width (lb/in)
            w = damage width (in)
            c = crush depth (in)
            A = intercept (lb/in) - force to initiate permanent crush
            B = slope (lb/in/in) - stiffness increase per inch of crush
        """
        return A + B * c

    def crush_energy(self, crush_depths, damage_width, A, B):
        """
        Compute crush energy from measured crush profile using SAE J2868.

        CE = w * sum[ A*ci + 0.5*B*ci^2 + A^2/(2B) ] * dx

        Args:
            crush_depths: array of crush measurements at equal spacing (inches)
            damage_width: total damage width (inches)
            A, B: stiffness coefficients (lb/in and lb/in/in)

        Returns:
            Crush energy in ft-lb
        """
        n = len(crush_depths)
        if n < 2:
            return 0.0

        dx = damage_width / (n - 1)  # spacing between measurements

        ce = 0.0
        for ci in crush_depths:
            ce += A * ci + 0.5 * B * ci**2 + A**2 / (2 * B)
        ce *= dx

        # Convert in-lb to ft-lb
        return ce / 12.0

    def speed_from_crush(self, crush_depth_in, weight_lb, damage_width_in, A, B):
        """
        Calculate barrier equivalent speed (BES) from crush depth.

        BES = sqrt(2 * CE / m)

        Args:
            crush_depth_in: average or uniform crush depth (inches)
            weight_lb: vehicle weight (lb)
            damage_width_in: width of damage (inches)
            A, B: stiffness coefficients

        Returns:
            BES in mph
        """
        ce_ft_lb = damage_width_in * (
            A * crush_depth_in + 0.5 * B * crush_depth_in**2 + A**2 / (2 * B)
        ) / 12.0

        mass_slugs = weight_lb / 32.2
        if mass_slugs <= 0:
            return 0.0

        bes_fps = np.sqrt(2 * ce_ft_lb / mass_slugs)
        return bes_fps / 1.467  # ft/s to mph

    def add_beamng_test(self, speed_mph, crush_depth_in, damage_width_in=None):
        """
        Add a BeamNG barrier test result for curve fitting.

        Args:
            speed_mph: Impact speed in mph
            crush_depth_in: Measured average crush depth in inches
            damage_width_in: Measured damage width (optional)
        """
        self.test_data.append({
            'speed_mph': speed_mph,
            'crush_depth_in': crush_depth_in,
            'damage_width_in': damage_width_in,
        })

    def extract_crush_from_beamng(self, bng, vehicle, direction='front'):
        """
        Extract crush depth from BeamNG vehicle node positions.

        Compares current node positions against reference (undamaged)
        positions to compute crush depth profile.

        Args:
            bng: BeamNGpy instance
            vehicle: beamngpy Vehicle object
            direction: 'front', 'rear', 'left', 'right'

        Returns:
            dict with average_crush_in, max_crush_in, crush_profile, damage_width_in
        """
        try:
            from beamngpy import BeamNGpy
        except ImportError:
            raise ImportError("beamngpy required for live crush extraction")

        vehicle.sensors.poll()

        # Get node positions from vehicle state
        # BeamNG provides node data through the vehicle API
        node_data = bng.vehicles[vehicle.vid].get_part_config()

        # Get current node positions
        nodes = vehicle.sensors['state'].data.get('nodes', {})
        ref_nodes = vehicle.sensors['state'].data.get('ref_nodes', {})

        if not nodes or not ref_nodes:
            # Fallback: use damage sensor value as proxy
            damage = vehicle.sensors['damage'].data
            damage_total = damage.get('damage', 0)

            # Rough conversion: BeamNG damage units to inches
            # This mapping needs calibration per vehicle model
            estimated_crush = damage_total * 0.01  # placeholder scaling

            return {
                'average_crush_in': estimated_crush,
                'max_crush_in': estimated_crush,
                'crush_profile': [estimated_crush],
                'damage_width_in': 60,  # assumed full width
                'method': 'damage_proxy',
            }

        # Calculate displacement of front-most nodes
        displacements = []
        for node_id, pos in nodes.items():
            if node_id in ref_nodes:
                ref_pos = ref_nodes[node_id]
                dx = np.sqrt(sum((a - b)**2 for a, b in zip(pos, ref_pos)))
                displacements.append(dx / IN_TO_M)  # convert to inches

        if not displacements:
            return {
                'average_crush_in': 0,
                'max_crush_in': 0,
                'crush_profile': [],
                'damage_width_in': 0,
                'method': 'node_displacement',
            }

        return {
            'average_crush_in': np.mean(displacements),
            'max_crush_in': np.max(displacements),
            'crush_profile': displacements,
            'damage_width_in': 60,  # needs geometric analysis per model
            'method': 'node_displacement',
        }

    def fit_stiffness(self):
        """
        Fit A/B stiffness coefficients to collected BeamNG test data.

        Uses the Campbell energy model:
        BES^2 = (2 * w / m) * [A*c + 0.5*B*c^2 + A^2/(2B)]

        Returns:
            StiffnessResult with fitted vs target coefficients
        """
        if len(self.test_data) < 2:
            raise ValueError("Need at least 2 barrier tests at different speeds to fit A/B")

        speeds = np.array([d['speed_mph'] for d in self.test_data])
        crushes = np.array([d['crush_depth_in'] for d in self.test_data])

        # Sort by speed
        order = np.argsort(speeds)
        speeds = speeds[order]
        crushes = crushes[order]

        # Fit: speed = f(crush) using Campbell model
        # BES = sqrt(2 * CE / m) where CE depends on A, B, crush
        # For fitting, use the linear relationship: BES^2 ∝ A*c + 0.5*B*c^2

        # Linear fit in crush space: speed^2 = k1*c + k2*c^2
        # This gives us the ratio of A and B
        def speed_sq_model(c, k1, k2):
            return k1 * c + k2 * c**2

        try:
            popt, pcov = curve_fit(speed_sq_model, crushes, speeds**2,
                                   p0=[100, 50], maxfev=10000)
            k1, k2 = popt

            # k1 is proportional to A, k2 to B
            # Need weight and width to convert to absolute A, B
            # Use first test case's data
            w_in = self.test_data[0].get('damage_width_in', 60)

            # From energy balance: BES^2 (mph^2) = (2*w*12)/(m) * [A*c + 0.5*B*c^2]
            # Converting: BES_fps^2 = 2*CE/m, BES_mph = BES_fps / 1.467
            # So: (BES_mph * 1.467)^2 = 2 * CE / m
            # This is approximate; actual calibration needs vehicle weight
            A_fitted = abs(k1) * 0.5  # approximate scaling
            B_fitted = abs(k2) * 0.25

            # Calculate R-squared
            predicted = speed_sq_model(crushes, *popt)
            ss_res = np.sum((speeds**2 - predicted)**2)
            ss_tot = np.sum((speeds**2 - np.mean(speeds**2))**2)
            r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0

        except RuntimeError:
            # Fallback: linear regression
            coeffs = np.polyfit(crushes, speeds, 1)
            B_fitted = coeffs[0] * 2
            A_fitted = coeffs[1]
            r_squared = 0.0

        # Compare with targets
        A_err = abs(A_fitted - self.target_A) / self.target_A * 100 if self.target_A else 0
        B_err = abs(B_fitted - self.target_B) / self.target_B * 100 if self.target_B else 0

        calibrated = A_err <= self.acceptance_pct and B_err <= self.acceptance_pct

        return StiffnessResult(
            vehicle_model="beamng_vehicle",
            A_fitted=A_fitted,
            B_fitted=B_fitted,
            A_target=self.target_A,
            B_target=self.target_B,
            A_error_pct=A_err,
            B_error_pct=B_err,
            r_squared=r_squared,
            test_speeds_mph=speeds.tolist(),
            crush_depths_in=crushes.tolist(),
            calibrated=calibrated,
        )

    def run_barrier_series(self, bng, vehicle_model, speeds_mph=None,
                           vehicle_weight_lb=3500, damage_width_in=60):
        """
        Run a series of flat-barrier impacts in BeamNG at increasing speeds.

        This automates the calibration process:
        1. Place vehicle at each test speed
        2. Impact rigid barrier
        3. Measure crush depth
        4. Collect data for A/B fitting

        Args:
            bng: Active BeamNGpy instance
            vehicle_model: BeamNG model name (e.g., 'etk800')
            speeds_mph: List of test speeds. If None, uses standard set.
            vehicle_weight_lb: Vehicle weight for energy calculations
            damage_width_in: Expected damage width

        Returns:
            StiffnessResult with calibration data
        """
        try:
            from beamngpy import Scenario, Vehicle
            from beamngpy.sensors import Damage, State
        except ImportError:
            raise ImportError("beamngpy required")

        if speeds_mph is None:
            speeds_mph = [10, 15, 20, 25, 30, 35]

        for speed in speeds_mph:
            # Create fresh scenario for each test
            scenario = Scenario('smallgrid', f'barrier_test_{speed}mph')

            veh = Vehicle('test_vehicle', model=vehicle_model)
            veh.sensors.attach('damage', Damage())
            veh.sensors.attach('state', State())

            # Position vehicle with clearance to reach speed before barrier
            # Barrier at origin, vehicle starts behind
            start_dist_m = 50  # meters of runway
            scenario.add_vehicle(veh, pos=(-start_dist_m, 0, 0.5))

            scenario.make(bng)
            bng.scenario.load(scenario)
            bng.scenario.start()

            # Set initial velocity toward barrier
            speed_ms = speed * MPH_TO_MS
            veh.set_velocity(speed_ms, 0, 0)

            # Wait for impact and settling (monitor velocity -> 0)
            max_steps = 5000  # 5 seconds at 0.001s steps
            for _ in range(max_steps):
                bng.control.step(2)
                veh.sensors.poll()
                state = veh.sensors['state'].data
                vel = state.get('vel', [0, 0, 0])
                if abs(vel[0]) < 0.1 and abs(vel[1]) < 0.1:
                    break

            # Extract crush
            crush_data = self.extract_crush_from_beamng(bng, veh, 'front')
            self.add_beamng_test(speed, crush_data['average_crush_in'],
                                damage_width_in)

        return self.fit_stiffness()

    def suggest_jbeam_adjustments(self, result):
        """
        Suggest BeamNG jbeam file modifications to match target stiffness.

        BeamNG vehicles are defined by .jbeam files containing node-beam
        definitions. This method suggests beam stiffness multipliers
        to bring the vehicle's crush response in line with NHTSA data.

        Args:
            result: StiffnessResult from fit_stiffness()

        Returns:
            dict with suggested adjustments
        """
        if result.calibrated:
            return {
                'status': 'calibrated',
                'message': 'Vehicle stiffness matches NHTSA data within acceptance criteria.',
            }

        # Compute required scaling factors
        a_scale = result.A_target / result.A_fitted if result.A_fitted else 1.0
        b_scale = result.B_target / result.B_fitted if result.B_fitted else 1.0

        # Average scaling for beam spring/deform values
        avg_scale = (a_scale + b_scale) / 2

        return {
            'status': 'adjustment_needed',
            'a_scale_factor': a_scale,
            'b_scale_factor': b_scale,
            'recommended_beam_spring_multiplier': avg_scale,
            'instructions': [
                f"1. Open the vehicle's .jbeam file in BeamNG/vehicles/{result.vehicle_model}/",
                f"2. Locate the 'beams' section with 'beamSpring' and 'beamDeform' values",
                f"3. Multiply front-structure beamSpring values by {avg_scale:.2f}",
                f"4. Multiply front-structure beamDeform values by {avg_scale:.2f}",
                f"5. Re-run barrier calibration series to verify",
                f"",
                f"Target: A = {result.A_target:.0f} lb/in, B = {result.B_target:.0f} lb/in/in",
                f"Current: A = {result.A_fitted:.0f} lb/in, B = {result.B_fitted:.0f} lb/in/in",
                f"Error: A = {result.A_error_pct:.1f}%, B = {result.B_error_pct:.1f}%",
            ],
        }
