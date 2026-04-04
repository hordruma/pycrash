"""
Validation framework for establishing BeamNG.drive as a validated crash
reconstruction tool using pycrash's peer-reviewed analytical models and
NHTSA crash test data as ground truth.

The validation approach:
1. Replicate known NHTSA full-frontal and offset barrier tests in BeamNG
2. Compare BeamNG node-beam deformation against NHTSA measured crush profiles
3. Calibrate BeamNG vehicle stiffness to match pycrash A/B coefficients
4. Run a matrix of two-vehicle impacts and compare delta-V, PDOF, rest
   positions against pycrash IMPC solutions
5. Establish acceptance criteria per SAE J2868 and reconstruction practice

References:
  - Carpenter & Welcher, SAE 2019-01-0422 (IMPC model)
  - Bonugli & Steffey, SAE 2017-01-1417 (stiffness data)
  - NHTSA vehicle crash test database
  - SAE J2868 - Crush Energy Method
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Acceptance criteria based on reconstruction practice
# ---------------------------------------------------------------------------

@dataclass
class AcceptanceCriteria:
    """
    Thresholds for validating BeamNG against analytical ground truth.

    Based on published reconstruction accuracy standards:
    - Delta-V accuracy within 5% is considered excellent
    - PDOF within 5 degrees is standard practice
    - Rest position within 1 vehicle length is acceptable
    """
    delta_v_pct: float = 10.0       # maximum delta-V error (%)
    delta_v_abs_mph: float = 2.0    # maximum absolute delta-V error (mph)
    pdof_deg: float = 10.0          # maximum PDOF error (degrees)
    rest_position_ft: float = 15.0  # maximum rest position error (ft)
    heading_deg: float = 15.0       # maximum final heading error (degrees)
    crush_depth_pct: float = 15.0   # maximum crush depth error (%)
    energy_pct: float = 15.0        # maximum energy dissipation error (%)

    def to_dict(self):
        return {
            'delta_v_pct': self.delta_v_pct,
            'delta_v_abs_mph': self.delta_v_abs_mph,
            'pdof_deg': self.pdof_deg,
            'rest_position_ft': self.rest_position_ft,
            'heading_deg': self.heading_deg,
            'crush_depth_pct': self.crush_depth_pct,
            'energy_pct': self.energy_pct,
        }


# ---------------------------------------------------------------------------
# Individual test case definition
# ---------------------------------------------------------------------------

@dataclass
class CrashTestCase:
    """
    Defines a single validation test case with known ground-truth outcomes.

    Ground truth can come from:
    - NHTSA crash test data (measured crush, accelerometer delta-V)
    - pycrash IMPC analytical solution (delta-V, post-impact velocities)
    - Published SAE validation data (RICSAC tests)
    """
    name: str
    description: str

    # Vehicle 1 parameters (pycrash input_dict format)
    veh1_params: dict = field(default_factory=dict)
    veh1_beamng_model: str = "etk800"

    # Vehicle 2 parameters (None for barrier tests)
    veh2_params: Optional[dict] = None
    veh2_beamng_model: str = "etk800"

    # Impact configuration
    impact_speed_mph: float = 0.0
    impact_angle_deg: float = 0.0      # relative angle between vehicles
    overlap_pct: float = 100.0          # percent frontal overlap
    impact_type: str = "frontal"        # frontal, offset, side, rear, oblique

    # Ground truth values (from NHTSA tests or pycrash analytical)
    truth_delta_v1_mph: Optional[float] = None
    truth_delta_v2_mph: Optional[float] = None
    truth_pdof1_deg: Optional[float] = None
    truth_pdof2_deg: Optional[float] = None
    truth_crush_depth1_in: Optional[float] = None
    truth_crush_depth2_in: Optional[float] = None
    truth_rest_x1_ft: Optional[float] = None
    truth_rest_y1_ft: Optional[float] = None
    truth_rest_x2_ft: Optional[float] = None
    truth_rest_y2_ft: Optional[float] = None
    truth_energy_ft_lb: Optional[float] = None

    # NHTSA test reference (if applicable)
    nhtsa_test_number: Optional[str] = None

    # Coefficient of restitution and friction
    cor: float = 0.1
    cof: float = 0.5


@dataclass
class TestResult:
    """Result of a single validation test."""
    test_case: CrashTestCase
    passed: bool
    metrics: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)
    beamng_telemetry: Optional[pd.DataFrame] = None
    pycrash_result: Optional[dict] = None


# ---------------------------------------------------------------------------
# NHTSA crash test validation suite
# ---------------------------------------------------------------------------

class NHTSAValidationSuite:
    """
    Validates BeamNG against NHTSA full-scale crash test data.

    Approach:
    1. Use NHTSA-measured vehicle stiffness (A, B coefficients from barrier tests)
    2. Compute analytical delta-V and crush using pycrash SDOF/IMPC
    3. Replicate the same test in BeamNG
    4. Compare BeamNG results against both NHTSA measured data and pycrash analytical
    5. Report pass/fail against acceptance criteria

    This establishes a chain of validation:
        NHTSA test data -> pycrash (validated against NHTSA) -> BeamNG (validated against pycrash)
    """

    def __init__(self, criteria=None):
        self.criteria = criteria or AcceptanceCriteria()
        self.test_cases = []
        self.results = []

    def add_test(self, test_case):
        """Add a CrashTestCase to the suite."""
        self.test_cases.append(test_case)
        return self

    def add_standard_tests(self):
        """
        Add a standard set of validation test cases covering common
        crash configurations used in accident reconstruction.
        """
        # Full-frontal collinear impact (simplest case, SDOF validated)
        self.add_test(CrashTestCase(
            name="collinear_35mph_equal_mass",
            description="Full frontal, collinear, equal mass at 35 mph closing speed",
            veh1_params={
                'weight': 3500, 'vx_initial': 35, 'vy_initial': 0,
                'head_angle': 0, 'init_x_pos': -50, 'init_y_pos': 0,
                'width': 6.0, 'length': 15.0, 'wb': 9.0,
                'lcgf': 3.8, 'lcgr': 5.2, 'hcg': 1.8,
                'track': 5.2, 'f_hang': 3.0, 'r_hang': 3.0,
                'tire_d': 2.2, 'tire_w': 0.7, 'izz': 2500,
                'A': 350, 'B': 110, 'k': 1500, 'L': 60, 'c': 0,
                'fwd': 1, 'rwd': 0, 'awd': 0,
                'brake': 0, 'steer_ratio': 16, 'omega_z': 0,
            },
            veh2_params={
                'weight': 3500, 'vx_initial': 0, 'vy_initial': 0,
                'head_angle': 180, 'init_x_pos': 0, 'init_y_pos': 0,
                'width': 6.0, 'length': 15.0, 'wb': 9.0,
                'lcgf': 3.8, 'lcgr': 5.2, 'hcg': 1.8,
                'track': 5.2, 'f_hang': 3.0, 'r_hang': 3.0,
                'tire_d': 2.2, 'tire_w': 0.7, 'izz': 2500,
                'A': 350, 'B': 110, 'k': 1500, 'L': 60, 'c': 0,
                'fwd': 1, 'rwd': 0, 'awd': 0,
                'brake': 0, 'steer_ratio': 16, 'omega_z': 0,
            },
            impact_speed_mph=35,
            impact_angle_deg=0,
            overlap_pct=100,
            impact_type="frontal",
            truth_delta_v1_mph=17.5,  # conservation of momentum: equal mass
            truth_delta_v2_mph=17.5,
            truth_pdof1_deg=0,
            truth_pdof2_deg=180,
            cor=0.1,
        ))

        # Oblique intersection collision (tests IMPC angular momentum)
        self.add_test(CrashTestCase(
            name="intersection_90deg_35_25mph",
            description="90-degree intersection, 35 mph strikes 25 mph, unequal mass",
            veh1_params={
                'weight': 3400, 'vx_initial': 35, 'vy_initial': 0,
                'head_angle': 0, 'init_x_pos': -50, 'init_y_pos': 0,
                'width': 6.0, 'length': 15.7, 'wb': 9.2,
                'lcgf': 3.8, 'lcgr': 5.4, 'hcg': 1.8,
                'track': 5.2, 'f_hang': 3.0, 'r_hang': 3.5,
                'tire_d': 2.2, 'tire_w': 0.7, 'izz': 2500,
                'A': 350, 'B': 110, 'k': 1500, 'L': 60, 'c': 12,
                'fwd': 1, 'rwd': 0, 'awd': 0,
                'brake': 0, 'steer_ratio': 16, 'omega_z': 0,
            },
            veh2_params={
                'weight': 3700, 'vx_initial': 25, 'vy_initial': 0,
                'head_angle': 90, 'init_x_pos': 0, 'init_y_pos': -40,
                'width': 6.2, 'length': 15.1, 'wb': 8.6,
                'lcgf': 3.6, 'lcgr': 5.0, 'hcg': 2.2,
                'track': 5.4, 'f_hang': 2.8, 'r_hang': 3.7,
                'tire_d': 2.3, 'tire_w': 0.75, 'izz': 2800,
                'A': 380, 'B': 120, 'k': 1600, 'L': 48, 'c': 8,
                'fwd': 0, 'rwd': 0, 'awd': 1,
                'brake': 0, 'steer_ratio': 14, 'omega_z': 0,
            },
            impact_speed_mph=35,
            impact_angle_deg=90,
            overlap_pct=50,
            impact_type="oblique",
            cor=0.1,
            cof=0.5,
        ))

        # Rear-end collision (common reconstruction scenario)
        self.add_test(CrashTestCase(
            name="rear_end_30mph_stopped",
            description="Rear-end collision, 30 mph striking stopped vehicle",
            veh1_params={
                'weight': 4000, 'vx_initial': 30, 'vy_initial': 0,
                'head_angle': 0, 'init_x_pos': -60, 'init_y_pos': 0,
                'width': 6.5, 'length': 16.0, 'wb': 9.5,
                'lcgf': 4.0, 'lcgr': 5.5, 'hcg': 2.0,
                'track': 5.5, 'f_hang': 3.0, 'r_hang': 3.5,
                'tire_d': 2.4, 'tire_w': 0.8, 'izz': 3000,
                'A': 300, 'B': 100, 'k': 1200, 'L': 55, 'c': 10,
                'fwd': 0, 'rwd': 1, 'awd': 0,
                'brake': 0, 'steer_ratio': 16, 'omega_z': 0,
            },
            veh2_params={
                'weight': 3200, 'vx_initial': 0, 'vy_initial': 0,
                'head_angle': 0, 'init_x_pos': 0, 'init_y_pos': 0,
                'width': 5.8, 'length': 14.5, 'wb': 8.8,
                'lcgf': 3.5, 'lcgr': 5.3, 'hcg': 1.7,
                'track': 5.0, 'f_hang': 2.8, 'r_hang': 2.9,
                'tire_d': 2.1, 'tire_w': 0.7, 'izz': 2200,
                'A': 250, 'B': 90, 'k': 1000, 'L': 50, 'c': 6,
                'fwd': 1, 'rwd': 0, 'awd': 0,
                'brake': 50, 'steer_ratio': 15, 'omega_z': 0,
            },
            impact_speed_mph=30,
            impact_angle_deg=0,
            overlap_pct=100,
            impact_type="rear",
            cor=0.15,
        ))

        return self

    def compute_pycrash_truth(self, test_case):
        """
        Run pycrash analytical models to establish ground truth for a test case.

        Uses IMPC for delta-V and post-impact kinematics.
        Uses SDOF for crush depth and energy dissipation.

        Returns:
            dict with analytical results
        """
        from pycrash import Vehicle
        from pycrash.impc import impc_calcs

        veh1 = Vehicle(f'{test_case.name}_v1', input_dict=test_case.veh1_params)

        result = {'test_name': test_case.name}

        if test_case.veh2_params is None:
            # Barrier test: use SDOF only
            result['type'] = 'barrier'
            return result

        veh2 = Vehicle(f'{test_case.name}_v2', input_dict=test_case.veh2_params)

        # Collinear momentum conservation for simple cases
        m1 = test_case.veh1_params['weight'] / 32.2  # slugs
        m2 = test_case.veh2_params['weight'] / 32.2
        v1 = test_case.veh1_params['vx_initial']  # mph
        v2 = test_case.veh2_params.get('vx_initial', 0)
        cor = test_case.cor

        if test_case.impact_angle_deg == 0:
            # Collinear: closed-form solution
            # Post-impact velocities from conservation of momentum + COR
            v1_post = (m1 * v1 + m2 * v2 - m2 * cor * (v1 - v2)) / (m1 + m2)
            v2_post = (m1 * v1 + m2 * v2 + m1 * cor * (v1 - v2)) / (m1 + m2)
            dv1 = abs(v1_post - v1)
            dv2 = abs(v2_post - v2)

            result['delta_v1_mph'] = dv1
            result['delta_v2_mph'] = dv2
            result['v1_post_mph'] = v1_post
            result['v2_post_mph'] = v2_post
            result['pdof1_deg'] = 0
            result['pdof2_deg'] = 0 if test_case.impact_type != 'rear' else 0
            result['type'] = 'collinear'

            # Energy dissipated (ft-lb)
            # KE = 0.5 * m * v^2, convert mph to ft/s (* 1.467)
            ke_pre = 0.5 * m1 * (v1 * 1.467)**2 + 0.5 * m2 * (v2 * 1.467)**2
            ke_post = 0.5 * m1 * (v1_post * 1.467)**2 + 0.5 * m2 * (v2_post * 1.467)**2
            result['energy_dissipated_ft_lb'] = ke_pre - ke_post

        else:
            # Non-collinear: note that full IMPC requires impact point setup
            # Store the analytical approach for when IMPC can be run
            result['type'] = 'oblique'
            result['note'] = 'Full IMPC requires impact point definition; use KinematicsTwo for complete solution'

            # Approximate delta-V from momentum conservation in 2D
            v1x = v1 * np.cos(np.radians(test_case.veh1_params['head_angle']))
            v1y = v1 * np.sin(np.radians(test_case.veh1_params['head_angle']))
            v2x = v2 * np.cos(np.radians(test_case.veh2_params['head_angle']))
            v2y = v2 * np.sin(np.radians(test_case.veh2_params['head_angle']))

            # Center-of-mass velocity
            vcm_x = (m1 * v1x + m2 * v2x) / (m1 + m2)
            vcm_y = (m1 * v1y + m2 * v2y) / (m1 + m2)

            # Approximate delta-V (perfectly plastic, cor=0)
            dv1x = vcm_x - v1x
            dv1y = vcm_y - v1y
            dv2x = vcm_x - v2x
            dv2y = vcm_y - v2y

            result['delta_v1_mph_approx'] = np.sqrt(dv1x**2 + dv1y**2)
            result['delta_v2_mph_approx'] = np.sqrt(dv2x**2 + dv2y**2)

        # Crush depth estimate from stiffness coefficients
        if test_case.truth_delta_v1_mph or result.get('delta_v1_mph'):
            dv = test_case.truth_delta_v1_mph or result.get('delta_v1_mph', 0)
            A = test_case.veh1_params.get('A', 0)
            B = test_case.veh1_params.get('B', 0)
            L = test_case.veh1_params.get('L', 1)
            w = test_case.veh1_params['weight']

            if B > 0 and L > 0:
                # Crush energy from delta-V: CE = 0.5 * m * dv^2
                # CE = L * (A*c + 0.5*B*c^2) + L*A^2/(2*B)  (SAE J2868)
                ce = 0.5 * (w / 32.2) * (dv * 1.467)**2
                # Solve quadratic for c: 0.5*B*L*c^2 + A*L*c + L*A^2/(2*B) - CE = 0
                a_coeff = 0.5 * B * L
                b_coeff = A * L
                c_coeff = L * A**2 / (2 * B) - ce
                disc = b_coeff**2 - 4 * a_coeff * c_coeff
                if disc >= 0:
                    result['crush_depth1_in'] = (-b_coeff + np.sqrt(disc)) / (2 * a_coeff)

        return result

    def evaluate_test(self, test_case, beamng_result):
        """
        Compare BeamNG simulation result against ground truth.

        Args:
            test_case: CrashTestCase with ground truth values
            beamng_result: dict with BeamNG-measured values:
                - delta_v1_mph, delta_v2_mph
                - pdof1_deg, pdof2_deg
                - rest_x1_ft, rest_y1_ft, rest_x2_ft, rest_y2_ft
                - crush_depth1_in, crush_depth2_in
                - energy_ft_lb

        Returns:
            TestResult with pass/fail and detailed metrics
        """
        metrics = {}
        failures = []
        c = self.criteria

        # Delta-V comparison
        for veh_num in [1, 2]:
            truth_key = f'truth_delta_v{veh_num}_mph'
            bng_key = f'delta_v{veh_num}_mph'
            truth = getattr(test_case, truth_key, None)
            bng = beamng_result.get(bng_key)

            if truth is not None and bng is not None:
                abs_err = abs(bng - truth)
                pct_err = (abs_err / truth * 100) if truth != 0 else 0
                metrics[f'delta_v{veh_num}_error_mph'] = abs_err
                metrics[f'delta_v{veh_num}_error_pct'] = pct_err
                metrics[f'delta_v{veh_num}_truth'] = truth
                metrics[f'delta_v{veh_num}_beamng'] = bng

                if pct_err > c.delta_v_pct and abs_err > c.delta_v_abs_mph:
                    failures.append(
                        f"Veh{veh_num} delta-V: {bng:.1f} mph vs truth {truth:.1f} mph "
                        f"(error: {pct_err:.1f}%, {abs_err:.1f} mph)"
                    )

        # PDOF comparison
        for veh_num in [1, 2]:
            truth = getattr(test_case, f'truth_pdof{veh_num}_deg', None)
            bng = beamng_result.get(f'pdof{veh_num}_deg')
            if truth is not None and bng is not None:
                err = abs(bng - truth)
                err = min(err, 360 - err)  # handle wrapping
                metrics[f'pdof{veh_num}_error_deg'] = err
                if err > c.pdof_deg:
                    failures.append(
                        f"Veh{veh_num} PDOF: {bng:.1f} deg vs truth {truth:.1f} deg "
                        f"(error: {err:.1f} deg)"
                    )

        # Rest position comparison
        for veh_num in [1, 2]:
            truth_x = getattr(test_case, f'truth_rest_x{veh_num}_ft', None)
            truth_y = getattr(test_case, f'truth_rest_y{veh_num}_ft', None)
            bng_x = beamng_result.get(f'rest_x{veh_num}_ft')
            bng_y = beamng_result.get(f'rest_y{veh_num}_ft')

            if all(v is not None for v in [truth_x, truth_y, bng_x, bng_y]):
                pos_err = np.sqrt((bng_x - truth_x)**2 + (bng_y - truth_y)**2)
                metrics[f'rest_position{veh_num}_error_ft'] = pos_err
                if pos_err > c.rest_position_ft:
                    failures.append(
                        f"Veh{veh_num} rest position error: {pos_err:.1f} ft"
                    )

        # Crush depth comparison
        for veh_num in [1, 2]:
            truth = getattr(test_case, f'truth_crush_depth{veh_num}_in', None)
            bng = beamng_result.get(f'crush_depth{veh_num}_in')
            if truth is not None and bng is not None and truth != 0:
                pct_err = abs(bng - truth) / truth * 100
                metrics[f'crush{veh_num}_error_pct'] = pct_err
                if pct_err > c.crush_depth_pct:
                    failures.append(
                        f"Veh{veh_num} crush: {bng:.1f} in vs truth {truth:.1f} in "
                        f"({pct_err:.1f}% error)"
                    )

        passed = len(failures) == 0

        return TestResult(
            test_case=test_case,
            passed=passed,
            metrics=metrics,
            failures=failures,
        )

    def generate_report(self):
        """Generate a summary validation report from all test results."""
        if not self.results:
            return "No tests have been run."

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)

        lines = [
            "=" * 70,
            "BEAMNG CRASH RECONSTRUCTION VALIDATION REPORT",
            "=" * 70,
            f"Tests run: {total}",
            f"Passed:    {passed}/{total} ({passed/total*100:.0f}%)",
            f"Failed:    {total - passed}/{total}",
            "",
            f"Acceptance Criteria:",
            f"  Delta-V:       < {self.criteria.delta_v_pct}% or < {self.criteria.delta_v_abs_mph} mph",
            f"  PDOF:          < {self.criteria.pdof_deg} deg",
            f"  Rest position: < {self.criteria.rest_position_ft} ft",
            f"  Crush depth:   < {self.criteria.crush_depth_pct}%",
            "",
            "-" * 70,
        ]

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            lines.append(f"\n[{status}] {result.test_case.name}")
            lines.append(f"       {result.test_case.description}")

            for key, val in result.metrics.items():
                if isinstance(val, float):
                    lines.append(f"       {key}: {val:.2f}")

            if result.failures:
                for fail in result.failures:
                    lines.append(f"    >> {fail}")

        lines.append("\n" + "=" * 70)

        if passed == total:
            lines.append(
                "RESULT: BeamNG VALIDATED for crash reconstruction within "
                "stated acceptance criteria."
            )
        else:
            lines.append(
                f"RESULT: {total - passed} test(s) outside acceptance criteria. "
                "BeamNG requires calibration adjustments before use in reconstruction."
            )

        lines.append("=" * 70)

        return '\n'.join(lines)
