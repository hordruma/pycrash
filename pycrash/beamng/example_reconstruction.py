"""
Example: Real Crash Reconstruction with pycrash + BeamNG.drive

This script demonstrates the full workflow:
1. Define vehicles with real crash data (from police report / scene evidence)
2. Run pycrash analytical reconstruction (IMPC model)
3. Build a BeamNG scenario from the reconstruction
4. Run the 3D simulation in BeamNG.tech
5. Compare analytical vs simulated results

Prerequisites:
    pip install beamngpy
    BeamNG.tech installed (set BEAMNG_HOME environment variable)

Usage:
    # Full workflow with BeamNG:
    python example_reconstruction.py --beamng

    # Analytical only (no BeamNG required):
    python example_reconstruction.py --analytical-only

    # Export scenario for manual BeamNG loading:
    python example_reconstruction.py --export scenario.json
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pycrash import Vehicle, KinematicsTwo


def create_example_vehicles():
    """
    Create two vehicles based on a typical intersection collision scenario.

    Vehicle 1: 2018 Toyota Camry traveling eastbound at 35 mph
    Vehicle 2: 2019 Honda CR-V traveling northbound at 25 mph
    Impact: Front of Veh1 strikes left side of Veh2
    """

    veh1_data = {
        'year': 2018,
        'make': 'Toyota',
        'model': 'Camry',
        'weight': 3400,            # lb
        'vin': '4T1B11HK5JU123456',
        'brake': 0,                # no braking pre-impact
        'steer_ratio': 15.8,
        'init_x_pos': -50,         # ft (50 ft west of impact point)
        'init_y_pos': 0,           # ft
        'head_angle': 0,           # deg (traveling east, along +X)
        'width': 6.0,              # ft
        'length': 15.7,            # ft
        'hcg': 1.8,               # ft
        'lcgf': 3.8,              # ft
        'lcgr': 5.4,              # ft
        'wb': 9.2,                # ft
        'track': 5.2,             # ft
        'f_hang': 3.0,            # ft
        'r_hang': 3.5,            # ft
        'tire_d': 2.2,            # ft
        'tire_w': 0.7,            # ft
        'izz': 2500,              # lb-ft-s^2
        'fwd': 1,
        'rwd': 0,
        'awd': 0,
        'A': 350,                 # lb/in (stiffness from NHTSA tests)
        'B': 110,                 # lb/in/in
        'k': 1500,                # lb/in effective stiffness
        'L': 60,                  # in (damage length)
        'c': 12,                  # in (crush depth from scene measurement)
        'vx_initial': 35,         # mph
        'vy_initial': 0,
        'omega_z': 0,
        'striking': True,
    }

    veh2_data = {
        'year': 2019,
        'make': 'Honda',
        'model': 'CR-V',
        'weight': 3700,
        'vin': '2HKRW2H55KH234567',
        'brake': 0,
        'steer_ratio': 14.3,
        'init_x_pos': 0,
        'init_y_pos': -40,        # 40 ft south of impact point
        'head_angle': 90,         # traveling north (+Y direction)
        'width': 6.2,
        'length': 15.1,
        'hcg': 2.2,
        'lcgf': 3.6,
        'lcgr': 5.0,
        'wb': 8.6,
        'track': 5.4,
        'f_hang': 2.8,
        'r_hang': 3.7,
        'tire_d': 2.3,
        'tire_w': 0.75,
        'izz': 2800,
        'fwd': 0,
        'rwd': 0,
        'awd': 1,
        'A': 380,
        'B': 120,
        'k': 1600,
        'L': 48,
        'c': 8,
        'vx_initial': 25,         # mph (in vehicle's forward direction)
        'vy_initial': 0,
        'omega_z': 0,
        'striking': False,
    }

    veh1 = Vehicle('Veh1_Camry', input_dict=veh1_data)
    veh2 = Vehicle('Veh2_CRV', input_dict=veh2_data)

    return veh1, veh2


def run_analytical_reconstruction(veh1, veh2):
    """Run pycrash IMPC analytical reconstruction."""
    print("\n--- Running pycrash Analytical Reconstruction ---")

    # Define impact parameters from scene evidence
    sim = KinematicsTwo(
        name='intersection_collision',
        impact_type='IMPC',
        veh1=veh1,
        veh2=veh2,
    )

    print("Analytical reconstruction complete.")
    print(f"  Vehicle 1 result rows: {len(sim.veh1.model) if hasattr(sim.veh1, 'model') else 'N/A'}")
    print(f"  Vehicle 2 result rows: {len(sim.veh2.model) if hasattr(sim.veh2, 'model') else 'N/A'}")

    return sim


def run_beamng_comparison(veh1, veh2, sim_result=None):
    """
    Build a BeamNG scenario and run side-by-side comparison.
    """
    from pycrash.beamng import ScenarioBuilder, TelemetryExtractor, ValidationComparator

    print("\n--- Building BeamNG Scenario ---")

    builder = ScenarioBuilder(level='smallgrid')

    # Map real vehicles to closest BeamNG equivalents
    builder.add_vehicle(veh1, beamng_model='etk800', color='White')
    builder.add_vehicle(veh2, beamng_model='etki', color='Red')

    # Option A: Export for manual loading
    scenario_file = 'intersection_reconstruction.json'
    builder.save_scenario(scenario_file, name='intersection_collision')
    print(f"Scenario exported to: {scenario_file}")

    # Option B: Run live in BeamNG (requires BeamNG.tech running)
    try:
        print("\nAttempting live BeamNG connection...")
        telemetry = builder.run_reconstruction(duration=5.0, dt=0.01)

        print("BeamNG simulation complete. Comparing results...")

        # Compare with pycrash analytical results
        if sim_result and hasattr(sim_result.veh1, 'model'):
            for veh_name, pc_veh, bng_df in [
                ('Veh1_Camry', sim_result.veh1, telemetry['Veh1_Camry']),
                ('Veh2_CRV', sim_result.veh2, telemetry['Veh2_CRV']),
            ]:
                comparator = ValidationComparator(
                    pycrash_df=pc_veh.model,
                    beamng_df=bng_df,
                    vehicle_name=veh_name,
                )
                report = comparator.summary_report()
                print(report['text'])

                # Extract delta-V from BeamNG
                extractor = TelemetryExtractor()
                extractor._raw_data = {veh_name: []}  # placeholder
                bng_dv = extractor.get_delta_v(veh_name)
                print(f"  BeamNG Delta-V: {bng_dv['delta_v_mph']:.1f} mph")

    except ImportError:
        print("beamngpy not installed. Install with: pip install beamngpy")
        print("Scenario JSON exported for manual use.")
    except ConnectionError:
        print("Could not connect to BeamNG.tech.")
        print("Ensure BeamNG.tech is running on localhost:64256")
        print("Scenario JSON exported for manual use.")

    return builder


def export_only(veh1, veh2, filepath):
    """Export scenario JSON without running BeamNG."""
    from pycrash.beamng import ScenarioBuilder

    builder = ScenarioBuilder(level='smallgrid')
    builder.add_vehicle(veh1, beamng_model='etk800', color='White')
    builder.add_vehicle(veh2, beamng_model='etki', color='Red')
    builder.save_scenario(filepath, name='intersection_collision')
    print(f"Scenario exported to: {filepath}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='pycrash + BeamNG crash reconstruction')
    parser.add_argument('--beamng', action='store_true', help='Run with BeamNG.tech')
    parser.add_argument('--analytical-only', action='store_true',
                        help='Run analytical reconstruction only')
    parser.add_argument('--export', type=str, help='Export scenario to JSON file')
    args = parser.parse_args()

    veh1, veh2 = create_example_vehicles()

    if args.export:
        export_only(veh1, veh2, args.export)
    elif args.analytical_only:
        run_analytical_reconstruction(veh1, veh2)
    else:
        sim = run_analytical_reconstruction(veh1, veh2)
        if args.beamng:
            run_beamng_comparison(veh1, veh2, sim)
        else:
            print("\nTo run with BeamNG, use: --beamng flag")
            print("To export scenario: --export scenario.json")
