"""
Example: Full Crash Reconstruction -> Injury Analysis Pipeline

    pycrash (validated) -> BeamNG (calibrated) -> OpenSim (biomechanics)

This script demonstrates the complete chain from vehicle-level crash
reconstruction to occupant injury risk assessment.

Scenario: 35 mph frontal collision, belted driver with frontal airbag.

Usage:
    # Analytical only (no BeamNG or OpenSim install needed):
    python example_full_pipeline.py

    # With BeamNG visualization:
    python example_full_pipeline.py --beamng

    # Full pipeline with OpenSim:
    python example_full_pipeline.py --opensim --model-path /path/to/Rajagopal2015.osim
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def run_pipeline(use_beamng=False, use_opensim=False, model_path=None):
    """
    Run the full pycrash -> BeamNG -> OpenSim pipeline.
    """

    print("=" * 60)
    print("CRASH RECONSTRUCTION -> INJURY ANALYSIS PIPELINE")
    print("=" * 60)

    # ---------------------------------------------------------------
    # STEP 1: pycrash Crash Reconstruction (Validated)
    # ---------------------------------------------------------------
    print("\n[STEP 1] pycrash Analytical Reconstruction")
    print("-" * 40)

    from pycrash.opensim.crash_pulse import CrashPulseGenerator
    from pycrash.opensim.injury_risk import InjuryRiskAssessment

    # Reconstruction inputs from scene evidence:
    #   - Crush measurements: 12 inches average on striking vehicle
    #   - Stiffness from NHTSA tests: A=350 lb/in, B=110 lb/in/in
    #   - Conservation of momentum yields delta-V = 17.5 mph
    #   - Impact duration estimated at 120ms (mid-size car frontal)
    delta_v_mph = 17.5
    duration_ms = 120
    print(f"  Delta-V: {delta_v_mph} mph (from crush/momentum analysis)")
    print(f"  Impact duration: {duration_ms} ms")

    # ---------------------------------------------------------------
    # STEP 2: Generate Occupant Crash Pulse
    # ---------------------------------------------------------------
    print("\n[STEP 2] Crash Pulse Generation")
    print("-" * 40)

    pulse = CrashPulseGenerator()

    # Set restraint system parameters
    pulse.set_restraint(
        belt_slack_in=1.0,
        belt_stiffness_lbf_in=500,
        airbag_deploy_ms=30,
        airbag_force_lb=800,
        occupant_weight_lb=170,     # 50th percentile male
    )

    # Generate pulse from reconstruction delta-V
    pulse.from_delta_v(delta_v_mph, duration_ms, pulse_shape='haversine')
    occupant_pulse = pulse.compute_occupant_pulse()

    summary = pulse.get_pulse_summary()
    print(f"  Peak vehicle acceleration: {summary['peak_accel_g']:.1f} g")
    print(f"  HIC15: {summary['hic_15']:.0f}")
    print(f"  HIC36: {summary['hic_36']:.0f}")
    print(f"  3ms clip: {summary['clip_3ms_g']:.1f} g")
    print(f"  Peak belt force: {summary['peak_belt_force_lb']:.0f} lb")
    print(f"  Max occupant excursion: {summary['max_occupant_excursion_in']:.1f} in")

    # ---------------------------------------------------------------
    # STEP 3: Injury Risk Assessment
    # ---------------------------------------------------------------
    print("\n[STEP 3] Injury Risk Assessment")
    print("-" * 40)

    injury = InjuryRiskAssessment()
    metrics = injury.from_pulse_summary(summary)
    print(injury.generate_report())

    # ---------------------------------------------------------------
    # STEP 4 (Optional): BeamNG 3D Validation
    # ---------------------------------------------------------------
    if use_beamng:
        print("\n[STEP 4] BeamNG 3D Simulation")
        print("-" * 40)
        try:
            from pycrash.beamng import ScenarioBuilder

            builder = ScenarioBuilder(level='smallgrid')
            # ... (see beamng/example_reconstruction.py for full BeamNG setup)
            print("  BeamNG scenario built. See beamng/example_reconstruction.py")

            # Could also use BeamNG telemetry as pulse source:
            # pulse.from_beamng_telemetry(beamng_df)
            # This compares analytical pulse vs simulated pulse
        except ImportError:
            print("  beamngpy not installed. Skipping BeamNG step.")

    # ---------------------------------------------------------------
    # STEP 5 (Optional): OpenSim Biomechanical Simulation
    # ---------------------------------------------------------------
    if use_opensim:
        print("\n[STEP 5] OpenSim Biomechanical Simulation")
        print("-" * 40)

        from pycrash.opensim.occupant_model import OccupantModel

        output_dir = os.path.join(os.getcwd(), 'opensim_output')

        model = OccupantModel('rajagopal_2015', model_path=model_path)

        # Generate all OpenSim input files
        setup = model.setup_analysis_pipeline(
            crash_pulse=pulse,
            output_dir=output_dir,
            duration_s=0.2,
        )

        print(f"  OpenSim files generated in: {output_dir}")
        for f in setup['force_files']:
            print(f"    {os.path.basename(f)}")

        print("\n  To run in OpenSim:")
        for instruction in setup['instructions']:
            print(f"    {instruction}")

        # If OpenSim is installed, run the simulation
        try:
            model.load_model()
            model.set_seated_posture()
            results = model.run_forward_dynamics(duration_s=0.2,
                                                  output_dir=output_dir)
            print(f"\n  Simulation complete. Results in: {output_dir}")

            # Get joint reaction forces for refined injury analysis
            joint_data = model.get_joint_reactions()
            print(f"  Analyzed joints: {joint_data['target_joints']}")

        except ImportError:
            print("\n  opensim package not installed.")
            print("  Force files are ready for manual loading in OpenSim GUI.")
        except FileNotFoundError as e:
            print(f"\n  {e}")
            print("  Force files are ready for manual loading in OpenSim GUI.")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  Reconstruction: delta-V = {delta_v_mph} mph, duration = {duration_ms} ms")
    print(f"  Occupant pulse: {summary['peak_accel_g']:.1f} g peak, HIC15 = {summary['hic_15']:.0f}")
    print(f"  Injury risk:    {metrics.overall_ais3_prob:.1%} AIS 3+ probability")
    print(f"  Validation:     pycrash (SAE 2021-01-0896)")
    if use_beamng:
        print(f"  3D simulation:  BeamNG.tech (calibrated against NHTSA)")
    if use_opensim:
        print(f"  Biomechanics:   OpenSim (Rajagopal 2015 model)")
    print("=" * 60)

    return {
        'delta_v_mph': delta_v_mph,
        'pulse_summary': summary,
        'injury_metrics': injury.to_dict(),
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Full crash reconstruction to injury analysis pipeline'
    )
    parser.add_argument('--beamng', action='store_true',
                        help='Include BeamNG 3D simulation step')
    parser.add_argument('--opensim', action='store_true',
                        help='Include OpenSim biomechanical analysis')
    parser.add_argument('--model-path', type=str, default=None,
                        help='Path to OpenSim .osim model file')
    args = parser.parse_args()

    run_pipeline(
        use_beamng=args.beamng,
        use_opensim=args.opensim,
        model_path=args.model_path,
    )
