"""
Automated test matrix runner for systematic BeamNG validation.

Sweeps across impact speed, angle, overlap, and mass ratio to build
a comprehensive validation dataset comparing BeamNG against pycrash
analytical solutions.

The test matrix approach follows SAE reconstruction validation practice:
a simulator is only as valid as the range of scenarios it has been tested against.
"""

import numpy as np
import pandas as pd
import itertools
import json
import os
from datetime import datetime
from dataclasses import dataclass

from .crash_test_validation import (
    CrashTestCase,
    NHTSAValidationSuite,
    AcceptanceCriteria,
)
from .vehicle_converter import FT_TO_M, MPH_TO_MS


# Default vehicle template for parametric sweeps
_DEFAULT_VEHICLE = {
    'width': 6.0, 'length': 15.0, 'wb': 9.0,
    'lcgf': 3.8, 'lcgr': 5.2, 'hcg': 1.8,
    'track': 5.2, 'f_hang': 3.0, 'r_hang': 3.0,
    'tire_d': 2.2, 'tire_w': 0.7, 'izz': 2500,
    'A': 350, 'B': 110, 'k': 1500, 'L': 60, 'c': 0,
    'fwd': 1, 'rwd': 0, 'awd': 0,
    'brake': 0, 'steer_ratio': 16, 'omega_z': 0,
    'vy_initial': 0,
}


@dataclass
class TestMatrixConfig:
    """Configuration for a parametric test matrix sweep."""
    speeds_mph: list           # closing speeds to test
    angles_deg: list           # relative impact angles
    overlap_pcts: list         # frontal overlap percentages
    mass_ratios: list          # veh1_weight / veh2_weight
    base_weight_lb: float = 3500.0
    cor_values: list = None    # coefficients of restitution
    cof_values: list = None    # coefficients of friction

    def __post_init__(self):
        if self.cor_values is None:
            self.cor_values = [0.1]
        if self.cof_values is None:
            self.cof_values = [0.5]

    @property
    def total_tests(self):
        return (len(self.speeds_mph) * len(self.angles_deg) *
                len(self.overlap_pcts) * len(self.mass_ratios) *
                len(self.cor_values) * len(self.cof_values))


def standard_matrix():
    """
    Standard validation matrix covering the most common reconstruction scenarios.

    This is the minimum set of tests needed to establish BeamNG validity.
    """
    return TestMatrixConfig(
        speeds_mph=[15, 25, 35, 45, 55],
        angles_deg=[0, 30, 60, 90, 120, 150, 180],
        overlap_pcts=[100, 75, 50, 25],
        mass_ratios=[0.7, 1.0, 1.3, 1.8],
        cor_values=[0.05, 0.1, 0.2],
        cof_values=[0.3, 0.5, 0.7],
    )


def quick_matrix():
    """Reduced matrix for rapid iteration during development."""
    return TestMatrixConfig(
        speeds_mph=[25, 35, 45],
        angles_deg=[0, 45, 90, 135, 180],
        overlap_pcts=[100, 50],
        mass_ratios=[1.0, 1.5],
        cor_values=[0.1],
        cof_values=[0.5],
    )


class TestMatrixRunner:
    """
    Generates and runs a parametric test matrix comparing BeamNG against pycrash.

    For each combination of parameters:
    1. Compute pycrash analytical solution (ground truth)
    2. Build and run corresponding BeamNG scenario
    3. Extract results and compare
    4. Log pass/fail against acceptance criteria
    """

    def __init__(self, config=None, criteria=None, output_dir=None):
        """
        Args:
            config: TestMatrixConfig defining the parameter sweep
            criteria: AcceptanceCriteria for pass/fail evaluation
            output_dir: Directory to save results (CSV, plots, reports)
        """
        self.config = config or quick_matrix()
        self.criteria = criteria or AcceptanceCriteria()
        self.output_dir = output_dir or os.path.join(os.getcwd(), 'beamng_validation')
        self.suite = NHTSAValidationSuite(self.criteria)
        self.results_df = None

    def generate_test_cases(self):
        """
        Generate all test cases from the parameter matrix.

        Returns:
            list of CrashTestCase objects
        """
        cases = []
        cfg = self.config

        combos = itertools.product(
            cfg.speeds_mph,
            cfg.angles_deg,
            cfg.overlap_pcts,
            cfg.mass_ratios,
            cfg.cor_values,
            cfg.cof_values,
        )

        for speed, angle, overlap, mass_ratio, cor, cof in combos:
            w1 = cfg.base_weight_lb * mass_ratio
            w2 = cfg.base_weight_lb

            # Build vehicle parameter dicts
            veh1_p = _DEFAULT_VEHICLE.copy()
            veh1_p.update({
                'weight': w1,
                'vx_initial': speed,
                'head_angle': 0,
                'init_x_pos': -60,
                'init_y_pos': 0,
                'izz': 2500 * (w1 / 3500),  # scale inertia with mass
            })

            veh2_p = _DEFAULT_VEHICLE.copy()
            veh2_p.update({
                'weight': w2,
                'vx_initial': 0,
                'head_angle': 180 - angle,  # facing veh1 at specified angle
                'init_x_pos': 0,
                'init_y_pos': 0,
                'izz': 2500,
            })

            name = f"s{speed}_a{angle}_o{overlap}_mr{mass_ratio:.1f}_cor{cor}_cof{cof}"

            case = CrashTestCase(
                name=name,
                description=(
                    f"{speed}mph, {angle}deg, {overlap}% overlap, "
                    f"mass ratio {mass_ratio:.1f}, COR={cor}, COF={cof}"
                ),
                veh1_params=veh1_p,
                veh2_params=veh2_p,
                impact_speed_mph=speed,
                impact_angle_deg=angle,
                overlap_pct=overlap,
                cor=cor,
                cof=cof,
            )

            # Compute pycrash ground truth and set as truth values
            truth = self.suite.compute_pycrash_truth(case)
            if 'delta_v1_mph' in truth:
                case.truth_delta_v1_mph = truth['delta_v1_mph']
                case.truth_delta_v2_mph = truth['delta_v2_mph']
            elif 'delta_v1_mph_approx' in truth:
                case.truth_delta_v1_mph = truth['delta_v1_mph_approx']
                case.truth_delta_v2_mph = truth['delta_v2_mph_approx']

            cases.append(case)

        return cases

    def run_analytical_only(self):
        """
        Run only the pycrash analytical solutions for all test cases.

        Use this to pre-compute ground truth before connecting to BeamNG.
        Results are saved as CSV for later comparison.

        Returns:
            DataFrame with analytical results for all test cases
        """
        cases = self.generate_test_cases()
        rows = []

        for case in cases:
            truth = self.suite.compute_pycrash_truth(case)
            row = {
                'name': case.name,
                'speed_mph': case.impact_speed_mph,
                'angle_deg': case.impact_angle_deg,
                'overlap_pct': case.overlap_pct,
                'mass_ratio': case.veh1_params['weight'] / case.veh2_params['weight'],
                'cor': case.cor,
                'cof': case.cof,
                'type': truth.get('type', 'unknown'),
            }
            row.update({k: v for k, v in truth.items()
                       if isinstance(v, (int, float))})
            rows.append(row)

        self.results_df = pd.DataFrame(rows)

        # Save to file
        os.makedirs(self.output_dir, exist_ok=True)
        filepath = os.path.join(
            self.output_dir,
            f'analytical_truth_{datetime.now():%Y%m%d_%H%M%S}.csv'
        )
        self.results_df.to_csv(filepath, index=False)

        return self.results_df

    def run_with_beamng(self, bng):
        """
        Run the full test matrix: pycrash analytical + BeamNG simulation.

        Args:
            bng: Active BeamNGpy instance

        Returns:
            DataFrame with comparison results
        """
        from .scenario_builder import ScenarioBuilder
        from .telemetry import TelemetryExtractor
        from pycrash import Vehicle

        cases = self.generate_test_cases()
        rows = []

        for i, case in enumerate(cases):
            print(f"Running test {i+1}/{len(cases)}: {case.name}")

            # Pycrash ground truth
            truth = self.suite.compute_pycrash_truth(case)

            # Build and run BeamNG scenario
            builder = ScenarioBuilder(level='smallgrid')
            veh1 = Vehicle(f'{case.name}_v1', input_dict=case.veh1_params)
            veh2 = Vehicle(f'{case.name}_v2', input_dict=case.veh2_params)
            builder.add_vehicle(veh1, color='White')
            builder.add_vehicle(veh2, color='Red')

            try:
                telemetry = builder.run_reconstruction(duration=5.0, dt=0.01)

                extractor = TelemetryExtractor()
                extractor._raw_data = telemetry  # wire up raw data

                bng_dv1 = extractor.get_delta_v(f'{case.name}_v1')
                bng_dv2 = extractor.get_delta_v(f'{case.name}_v2')

                bng_result = {
                    'delta_v1_mph': bng_dv1['delta_v_mph'],
                    'delta_v2_mph': bng_dv2['delta_v_mph'],
                }

                # Evaluate against criteria
                test_result = self.suite.evaluate_test(case, bng_result)
                self.suite.results.append(test_result)

                row = {
                    'name': case.name,
                    'speed_mph': case.impact_speed_mph,
                    'angle_deg': case.impact_angle_deg,
                    'overlap_pct': case.overlap_pct,
                    'mass_ratio': case.veh1_params['weight'] / case.veh2_params['weight'],
                    'cor': case.cor,
                    'passed': test_result.passed,
                    'pycrash_dv1': truth.get('delta_v1_mph', truth.get('delta_v1_mph_approx')),
                    'beamng_dv1': bng_dv1['delta_v_mph'],
                    'pycrash_dv2': truth.get('delta_v2_mph', truth.get('delta_v2_mph_approx')),
                    'beamng_dv2': bng_dv2['delta_v_mph'],
                }
                row.update(test_result.metrics)
                rows.append(row)

            except Exception as e:
                print(f"  ERROR: {e}")
                rows.append({
                    'name': case.name,
                    'speed_mph': case.impact_speed_mph,
                    'angle_deg': case.impact_angle_deg,
                    'passed': False,
                    'error': str(e),
                })

        self.results_df = pd.DataFrame(rows)

        os.makedirs(self.output_dir, exist_ok=True)
        filepath = os.path.join(
            self.output_dir,
            f'validation_results_{datetime.now():%Y%m%d_%H%M%S}.csv'
        )
        self.results_df.to_csv(filepath, index=False)

        return self.results_df

    def summary_statistics(self):
        """
        Compute summary statistics across the full test matrix.

        Returns:
            dict with overall pass rate, error distributions by parameter
        """
        if self.results_df is None or self.results_df.empty:
            return {'error': 'No results available. Run tests first.'}

        df = self.results_df

        stats = {
            'total_tests': len(df),
            'passed': int(df['passed'].sum()) if 'passed' in df.columns else 0,
            'pass_rate_pct': float(df['passed'].mean() * 100) if 'passed' in df.columns else 0,
        }

        # Error distributions by parameter
        if 'delta_v1_error_pct' in df.columns:
            stats['delta_v1_error'] = {
                'mean_pct': float(df['delta_v1_error_pct'].mean()),
                'std_pct': float(df['delta_v1_error_pct'].std()),
                'max_pct': float(df['delta_v1_error_pct'].max()),
                'median_pct': float(df['delta_v1_error_pct'].median()),
            }

        # Pass rate by impact angle
        if 'angle_deg' in df.columns and 'passed' in df.columns:
            by_angle = df.groupby('angle_deg')['passed'].mean() * 100
            stats['pass_rate_by_angle'] = by_angle.to_dict()

        # Pass rate by speed
        if 'speed_mph' in df.columns and 'passed' in df.columns:
            by_speed = df.groupby('speed_mph')['passed'].mean() * 100
            stats['pass_rate_by_speed'] = by_speed.to_dict()

        # Pass rate by mass ratio
        if 'mass_ratio' in df.columns and 'passed' in df.columns:
            by_mass = df.groupby('mass_ratio')['passed'].mean() * 100
            stats['pass_rate_by_mass_ratio'] = by_mass.to_dict()

        return stats

    def print_summary(self):
        """Print a human-readable summary of test matrix results."""
        stats = self.summary_statistics()
        if 'error' in stats:
            print(stats['error'])
            return

        print("=" * 60)
        print("BEAMNG VALIDATION TEST MATRIX SUMMARY")
        print("=" * 60)
        print(f"Total tests:  {stats['total_tests']}")
        print(f"Passed:       {stats['passed']}/{stats['total_tests']} "
              f"({stats['pass_rate_pct']:.1f}%)")

        if 'delta_v1_error' in stats:
            dv = stats['delta_v1_error']
            print(f"\nDelta-V Error Distribution:")
            print(f"  Mean:   {dv['mean_pct']:.1f}%")
            print(f"  Median: {dv['median_pct']:.1f}%")
            print(f"  Std:    {dv['std_pct']:.1f}%")
            print(f"  Max:    {dv['max_pct']:.1f}%")

        if 'pass_rate_by_angle' in stats:
            print(f"\nPass Rate by Impact Angle:")
            for angle, rate in sorted(stats['pass_rate_by_angle'].items()):
                bar = '#' * int(rate / 5)
                print(f"  {angle:>5.0f} deg: {rate:5.1f}% {bar}")

        if 'pass_rate_by_speed' in stats:
            print(f"\nPass Rate by Closing Speed:")
            for speed, rate in sorted(stats['pass_rate_by_speed'].items()):
                bar = '#' * int(rate / 5)
                print(f"  {speed:>4.0f} mph: {rate:5.1f}% {bar}")

        print("=" * 60)
