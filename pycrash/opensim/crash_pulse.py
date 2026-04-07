"""
Generates occupant crash pulses from pycrash reconstruction data and
BeamNG telemetry for input to OpenSim biomechanical simulation.

The crash pulse is the acceleration-time history experienced by the occupant
during the collision. This module converts vehicle-level delta-V and
acceleration data into occupant-level forces applied to the OpenSim model.

Key concepts:
- Vehicle acceleration pulse comes from pycrash SDOF model or BeamNG telemetry
- Occupant kinematics lag behind the vehicle (ride-down effect)
- Restraint system (seatbelt, airbag) modifies the pulse shape and peak
- Output formats: OpenSim .sto files and ExternalLoads .xml

References:
  - Huang, M. (2002) Vehicle Crash Mechanics, CRC Press
  - Schmitt et al. (2019) Trauma Biomechanics, Springer
"""

import numpy as np
import pandas as pd
import os
from typing import Optional


# Unit conversions
G_FTS2 = 32.174    # ft/s^2 per g
G_MS2 = 9.80665    # m/s^2 per g
MPH_TO_FTS = 1.46667
MPH_TO_MS = 0.44704
FT_TO_M = 0.3048
LB_TO_N = 4.44822
LB_TO_KG = 0.453592


class CrashPulseGenerator:
    """
    Generates occupant crash pulses from vehicle-level reconstruction data.

    Three sources of vehicle acceleration data:
    1. pycrash SDOF model output (validated analytical)
    2. BeamNG telemetry (simulation)
    3. Synthetic half-sine or haversine pulse from delta-V and duration

    The pulse is then modified by restraint parameters to produce the
    occupant-experienced acceleration for OpenSim input.
    """

    def __init__(self):
        self._vehicle_pulse = None
        self._occupant_pulse = None
        self._restraint_params = {
            'belt_slack_in': 1.0,        # seatbelt slack (inches)
            'belt_stiffness_lbf_in': 500, # seatbelt stiffness (lb/in)
            'airbag_deploy_ms': 30,       # airbag deployment time
            'airbag_force_lb': 800,       # peak airbag force
            'occupant_weight_lb': 170,    # 50th percentile male
            'seated_height_in': 35,       # torso height seated
        }

    def set_restraint(self, **kwargs):
        """
        Set restraint system parameters.

        Args:
            belt_slack_in: Seatbelt slack before engagement (inches)
            belt_stiffness_lbf_in: Belt stiffness after engagement (lb/in)
            airbag_deploy_ms: Time to airbag deployment (ms)
            airbag_force_lb: Peak airbag force on occupant (lb)
            occupant_weight_lb: Occupant weight (lb)
            seated_height_in: Seated torso height for moment arm (inches)
        """
        for k, v in kwargs.items():
            if k in self._restraint_params:
                self._restraint_params[k] = v
            else:
                raise ValueError(f"Unknown restraint parameter: {k}")
        return self

    def from_sdof(self, sdof_result):
        """
        Extract vehicle crash pulse from a pycrash SDOF_Model result.

        The SDOF model provides vehicle acceleration during impact at
        dt_impact = 0.0001s resolution - ideal for crash pulse analysis.

        Args:
            sdof_result: pycrash SDOF_Model instance (after simulation)

        Returns:
            self for method chaining
        """
        if not hasattr(sdof_result, 'model'):
            raise ValueError("SDOF result has no model data. Run simulation first.")

        model = sdof_result.model

        self._vehicle_pulse = pd.DataFrame({
            't_s': model['t'].values,
            'accel_g': model['a1'].values / G_FTS2,  # ft/s^2 to g
            'velocity_fps': model['v1'].values,
            'displacement_ft': model['x1'].values,
        })

        return self

    def from_beamng_telemetry(self, telemetry_df, vehicle_frame=True):
        """
        Extract vehicle crash pulse from BeamNG telemetry DataFrame.

        Args:
            telemetry_df: DataFrame from TelemetryExtractor (pycrash format)
            vehicle_frame: If True, use vehicle-frame acceleration (au).
                          If False, use world-frame (ax).

        Returns:
            self for method chaining
        """
        accel_col = 'au' if vehicle_frame else 'ax'
        if accel_col not in telemetry_df.columns:
            raise ValueError(f"Column '{accel_col}' not in telemetry DataFrame")

        self._vehicle_pulse = pd.DataFrame({
            't_s': telemetry_df['t'].values,
            'accel_g': telemetry_df[accel_col].values / G_FTS2,
            'velocity_fps': telemetry_df.get('vx', telemetry_df.get('Vx', 0)).values if 'vx' in telemetry_df else np.zeros(len(telemetry_df)),
        })

        return self

    def from_delta_v(self, delta_v_mph, duration_ms, pulse_shape='haversine',
                     dt_ms=0.1):
        """
        Generate synthetic crash pulse from delta-V and impact duration.

        This is the most common input in reconstruction practice:
        the analyst knows delta-V (from crush analysis or momentum) and
        estimates impact duration from vehicle class.

        Args:
            delta_v_mph: Change in velocity during impact (mph)
            duration_ms: Impact duration in milliseconds (typically 80-150ms)
            pulse_shape: 'haversine', 'half_sine', 'triangular', or 'square'
            dt_ms: Time step in milliseconds

        Returns:
            self for method chaining
        """
        delta_v_fps = delta_v_mph * MPH_TO_FTS
        duration_s = duration_ms / 1000.0
        n_steps = int(duration_ms / dt_ms) + 1
        t = np.linspace(0, duration_s, n_steps)

        if pulse_shape == 'haversine':
            # Haversine: a(t) = A * (1 - cos(2*pi*t/T)) / 2
            # Integrates to delta_v = A * T / 2
            peak_g = (2 * delta_v_fps / duration_s) / G_FTS2
            accel_g = peak_g * (1 - np.cos(2 * np.pi * t / duration_s)) / 2

        elif pulse_shape == 'half_sine':
            # Half-sine: a(t) = A * sin(pi*t/T)
            # Integrates to delta_v = 2*A*T/pi
            peak_g = (np.pi * delta_v_fps / (2 * duration_s)) / G_FTS2
            accel_g = peak_g * np.sin(np.pi * t / duration_s)

        elif pulse_shape == 'triangular':
            # Triangular: peak at t=T/2
            peak_g = (2 * delta_v_fps / duration_s) / G_FTS2
            accel_g = np.where(
                t <= duration_s / 2,
                peak_g * 2 * t / duration_s,
                peak_g * 2 * (1 - t / duration_s)
            )

        elif pulse_shape == 'square':
            peak_g = (delta_v_fps / duration_s) / G_FTS2
            accel_g = np.full_like(t, peak_g)

        else:
            raise ValueError(f"Unknown pulse shape: {pulse_shape}")

        # Integrate acceleration to get velocity and displacement
        velocity_fps = np.cumsum(accel_g * G_FTS2) * (t[1] - t[0]) if len(t) > 1 else np.zeros_like(t)

        self._vehicle_pulse = pd.DataFrame({
            't_s': t,
            'accel_g': accel_g,
            'velocity_fps': velocity_fps,
        })

        return self

    def compute_occupant_pulse(self):
        """
        Compute occupant-experienced pulse accounting for restraint ride-down.

        The occupant pulse differs from the vehicle pulse because:
        1. Seatbelt slack creates a delay before load onset
        2. Belt elasticity spreads the pulse over a longer duration
        3. Airbag provides distributed force on upper body
        4. Occupant mass and position affect effective acceleration

        Returns:
            DataFrame with occupant acceleration, force, and displacement
        """
        if self._vehicle_pulse is None:
            raise ValueError("No vehicle pulse set. Use from_sdof(), from_beamng_telemetry(), or from_delta_v() first.")

        vp = self._vehicle_pulse.copy()
        rp = self._restraint_params

        t = vp['t_s'].values
        dt = t[1] - t[0] if len(t) > 1 else 0.0001
        veh_accel_fps2 = vp['accel_g'].values * G_FTS2

        occ_mass_slugs = rp['occupant_weight_lb'] / 32.174

        # Simple occupant ride-down model:
        # Occupant is a lumped mass connected to vehicle via belt spring
        # F_belt = k * max(0, x_occ - x_veh - slack)
        # F_airbag = ramp function after deployment time

        belt_k = rp['belt_stiffness_lbf_in'] * 12  # convert to lb/ft
        slack_ft = rp['belt_slack_in'] / 12
        airbag_deploy_s = rp['airbag_deploy_ms'] / 1000
        airbag_peak_lb = rp['airbag_force_lb']

        # Integrate vehicle displacement from acceleration
        veh_vel = np.cumsum(veh_accel_fps2) * dt
        veh_disp = np.cumsum(veh_vel) * dt

        # Occupant state
        occ_vel = np.zeros_like(t)
        occ_disp = np.zeros_like(t)
        occ_accel = np.zeros_like(t)
        belt_force = np.zeros_like(t)
        airbag_force = np.zeros_like(t)

        for i in range(1, len(t)):
            # Relative displacement (occupant moves forward relative to vehicle)
            rel_disp = occ_disp[i-1] - veh_disp[i-1]

            # Belt force (tension only, after slack taken up)
            if rel_disp > slack_ft:
                belt_force[i] = -belt_k * (rel_disp - slack_ft)
            else:
                belt_force[i] = 0

            # Airbag force (ramps up after deployment, then decays)
            if t[i] > airbag_deploy_s:
                t_since_deploy = t[i] - airbag_deploy_s
                airbag_duration = 0.060  # 60ms airbag interaction
                if t_since_deploy < airbag_duration:
                    # Ramp up then down
                    phase = t_since_deploy / airbag_duration
                    airbag_force[i] = -airbag_peak_lb * np.sin(np.pi * phase)
                else:
                    airbag_force[i] = 0

            # Total force on occupant
            total_force = belt_force[i] + airbag_force[i]

            # Occupant acceleration
            occ_accel[i] = total_force / occ_mass_slugs

            # Integrate occupant motion
            occ_vel[i] = occ_vel[i-1] + occ_accel[i] * dt
            occ_disp[i] = occ_disp[i-1] + occ_vel[i] * dt

        self._occupant_pulse = pd.DataFrame({
            't_s': t,
            'occ_accel_g': occ_accel / G_FTS2,
            'occ_accel_fps2': occ_accel,
            'occ_velocity_fps': occ_vel,
            'occ_displacement_ft': occ_disp,
            'veh_accel_g': vp['accel_g'].values,
            'veh_displacement_ft': veh_disp,
            'belt_force_lb': belt_force,
            'airbag_force_lb': airbag_force,
            'relative_disp_ft': occ_disp - veh_disp,
        })

        return self._occupant_pulse

    def to_opensim_sto(self, filepath, body_segment='torso'):
        """
        Export occupant pulse as an OpenSim .sto (storage) file.

        Creates a time-series force file that can be loaded as ExternalLoads
        in OpenSim for forward or inverse dynamics analysis.

        Args:
            filepath: Output .sto file path
            body_segment: Body segment the force acts on ('torso', 'pelvis', 'head')

        Returns:
            filepath of written file
        """
        if self._occupant_pulse is None:
            self.compute_occupant_pulse()

        pulse = self._occupant_pulse
        occ_weight = self._restraint_params['occupant_weight_lb']

        # Convert to OpenSim coordinate system: +X forward, +Y up, +Z right
        # Crash pulse is primarily in X (fore-aft) direction
        # Force = mass * acceleration
        mass_kg = occ_weight * LB_TO_KG
        force_x = pulse['occ_accel_fps2'].values * mass_kg * FT_TO_M  # Newtons
        force_y = np.zeros(len(pulse))  # vertical
        force_z = np.zeros(len(pulse))  # lateral

        # Torque from force offset (moment arm from CG to application point)
        # For frontal impact, primary torque is about Z-axis (flexion)
        seated_height_m = self._restraint_params['seated_height_in'] * 0.0254
        if body_segment == 'torso':
            # Belt force acts at chest level, ~60% of seated height
            moment_arm_m = seated_height_m * 0.6
        elif body_segment == 'pelvis':
            moment_arm_m = 0.0  # force through pelvis CG
        elif body_segment == 'head':
            moment_arm_m = seated_height_m
        else:
            moment_arm_m = 0.0

        torque_z = force_x * moment_arm_m  # flexion torque (Nm)

        # Build .sto content
        n_rows = len(pulse)
        header = (
            f"{body_segment}_crash_forces\n"
            f"version=1\n"
            f"nRows={n_rows}\n"
            f"nColumns=10\n"
            f"inDegrees=no\n"
            f"endheader\n"
            f"time\t"
            f"{body_segment}_force_vx\t{body_segment}_force_vy\t{body_segment}_force_vz\t"
            f"{body_segment}_force_px\t{body_segment}_force_py\t{body_segment}_force_pz\t"
            f"{body_segment}_torque_x\t{body_segment}_torque_y\t{body_segment}_torque_z"
        )

        lines = [header]
        for i in range(n_rows):
            t = pulse['t_s'].iloc[i]
            # Force components (vx, vy, vz), application point (px, py, pz), torques
            line = (f"{t:.6f}\t"
                    f"{force_x[i]:.4f}\t{force_y[i]:.4f}\t{force_z[i]:.4f}\t"
                    f"0.0\t{moment_arm_m:.4f}\t0.0\t"
                    f"0.0\t0.0\t{torque_z[i]:.4f}")
            lines.append(line)

        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))

        return filepath

    def to_opensim_external_loads(self, filepath, sto_filepath,
                                   body_segment='torso',
                                   opensim_body='torso'):
        """
        Generate an OpenSim ExternalLoads XML file pointing to the .sto data.

        This XML file tells OpenSim how to apply the crash forces to the
        musculoskeletal model during simulation.

        Args:
            filepath: Output .xml file path
            sto_filepath: Path to the .sto file (from to_opensim_sto)
            body_segment: Label prefix used in the .sto file
            opensim_body: OpenSim body name to apply force to
                         ('torso', 'pelvis', 'head', etc.)

        Returns:
            filepath of written file
        """
        xml_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<OpenSimDocument Version="40000">
    <ExternalLoads name="crash_forces">
        <objects>
            <ExternalForce name="{body_segment}_crash_force">
                <applied_to_body>{opensim_body}</applied_to_body>
                <force_expressed_in_body>ground</force_expressed_in_body>
                <point_expressed_in_body>ground</point_expressed_in_body>
                <force_identifier>{body_segment}_force_v</force_identifier>
                <point_identifier>{body_segment}_force_p</point_identifier>
                <torque_identifier>{body_segment}_torque_</torque_identifier>
            </ExternalForce>
        </objects>
        <datafile>{sto_filepath}</datafile>
    </ExternalLoads>
</OpenSimDocument>"""

        with open(filepath, 'w') as f:
            f.write(xml_content)

        return filepath

    def get_pulse_summary(self):
        """
        Return key pulse metrics used in injury biomechanics.

        Returns:
            dict with peak acceleration, HIC, duration, delta-V
        """
        if self._occupant_pulse is None:
            self.compute_occupant_pulse()

        pulse = self._occupant_pulse
        t = pulse['t_s'].values
        a_g = np.abs(pulse['occ_accel_g'].values)

        peak_g = float(np.max(a_g))
        duration_ms = float((t[-1] - t[0]) * 1000)

        # HIC (Head Injury Criterion) calculation
        # HIC = max{ (t2-t1) * [1/(t2-t1) * integral(a dt)]^2.5 }
        # Computed over all intervals within 15ms or 36ms window
        hic_15 = self._compute_hic(t, a_g, window_ms=15)
        hic_36 = self._compute_hic(t, a_g, window_ms=36)

        # 3ms clip (peak average acceleration over 3ms)
        clip_3ms = self._compute_clip(t, a_g, window_ms=3)

        # Delta-V from occupant pulse
        dt = t[1] - t[0] if len(t) > 1 else 0.0001
        delta_v_fps = float(np.sum(np.abs(pulse['occ_accel_fps2'].values)) * dt)
        delta_v_mph = delta_v_fps / MPH_TO_FTS

        return {
            'peak_accel_g': peak_g,
            'hic_15': hic_15,
            'hic_36': hic_36,
            'clip_3ms_g': clip_3ms,
            'duration_ms': duration_ms,
            'delta_v_mph': delta_v_mph,
            'peak_belt_force_lb': float(np.max(np.abs(pulse['belt_force_lb'].values))),
            'peak_airbag_force_lb': float(np.max(np.abs(pulse['airbag_force_lb'].values))),
            'max_occupant_excursion_in': float(np.max(np.abs(pulse['relative_disp_ft'].values)) * 12),
        }

    @staticmethod
    def _compute_hic(t, a_g, window_ms=15):
        """
        Compute Head Injury Criterion over specified window.

        HIC = max over (t1,t2) of:
            (t2-t1) * [1/(t2-t1) * integral_t1^t2(a(t)dt)]^2.5

        where t2-t1 <= window_ms/1000
        """
        if len(t) < 2:
            return 0.0

        dt = t[1] - t[0]
        window_s = window_ms / 1000.0
        max_span = int(window_s / dt) + 1

        hic_max = 0.0
        for i in range(len(t)):
            j_end = min(i + max_span, len(t))
            for j in range(i + 1, j_end):
                interval = t[j] - t[i]
                if interval <= 0:
                    continue
                avg_a = np.trapz(a_g[i:j+1], t[i:j+1]) / interval
                hic = interval * (avg_a ** 2.5)
                if hic > hic_max:
                    hic_max = hic

        return float(hic_max)

    @staticmethod
    def _compute_clip(t, a_g, window_ms=3):
        """Compute clip value: peak average acceleration over window."""
        if len(t) < 2:
            return float(np.max(a_g)) if len(a_g) > 0 else 0.0

        dt = t[1] - t[0]
        window_steps = max(1, int(window_ms / 1000.0 / dt))

        max_avg = 0.0
        for i in range(len(a_g) - window_steps + 1):
            avg = np.mean(a_g[i:i + window_steps])
            if avg > max_avg:
                max_avg = avg

        return float(max_avg)
