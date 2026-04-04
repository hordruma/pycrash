"""
Extracts telemetry data from BeamNG.tech simulations into pycrash-compatible
Pandas DataFrames.

The telemetry data matches pycrash's output format (column names, units) so that
BeamNG results can be directly compared with analytical reconstruction results.
"""

import numpy as np
import pandas as pd

from .vehicle_converter import FT_TO_M, LB_TO_KG, MPH_TO_MS, DEG_TO_RAD


class TelemetryExtractor:
    """
    Records and converts BeamNG.tech vehicle telemetry into pycrash DataFrames.

    Captures:
    - Position, velocity, acceleration in both vehicle and world frames
    - Yaw angle, yaw rate, yaw acceleration
    - Wheel/tire forces and slip angles
    - Damage/deformation data (crush depth equivalent)
    - Node-beam deformation for energy analysis
    """

    def __init__(self):
        self._raw_data = {}

    def record(self, bng, vehicles, duration=10.0, dt=0.01):
        """
        Run a BeamNG simulation and record telemetry for all vehicles.

        Args:
            bng: Active BeamNGpy instance (scenario already started)
            vehicles: dict of {name: beamngpy.Vehicle} objects
            duration: Recording duration in seconds
            dt: Time step between samples in seconds

        Returns:
            dict of {vehicle_name: pandas.DataFrame} with pycrash-compatible columns
        """
        steps = int(duration / dt)
        raw = {name: [] for name in vehicles}

        for step_i in range(steps):
            bng.control.step(int(dt / 0.0005))  # BeamNG physics step is 0.5ms

            for name, veh in vehicles.items():
                veh.sensors.poll()
                state = veh.sensors['state'].data
                damage = veh.sensors['damage'].data
                electrics = veh.sensors['electrics'].data

                raw[name].append({
                    't': step_i * dt,
                    'pos_x': state.get('pos', [0, 0, 0])[0],
                    'pos_y': state.get('pos', [0, 0, 0])[1],
                    'pos_z': state.get('pos', [0, 0, 0])[2],
                    'vel_x': state.get('vel', [0, 0, 0])[0],
                    'vel_y': state.get('vel', [0, 0, 0])[1],
                    'vel_z': state.get('vel', [0, 0, 0])[2],
                    'rot_x': state.get('rot', [0, 0, 0, 1])[0],
                    'rot_y': state.get('rot', [0, 0, 0, 1])[1],
                    'rot_z': state.get('rot', [0, 0, 0, 1])[2],
                    'rot_w': state.get('rot', [0, 0, 0, 1])[3],
                    'ang_vel_x': state.get('ang_vel', [0, 0, 0])[0],
                    'ang_vel_y': state.get('ang_vel', [0, 0, 0])[1],
                    'ang_vel_z': state.get('ang_vel', [0, 0, 0])[2],
                    'damage_total': damage.get('damage', 0),
                    'deform_group_damage': damage.get('deform_group_damage', {}),
                    'wheel_speed_fl': electrics.get('wheelspeed_FL', 0),
                    'wheel_speed_fr': electrics.get('wheelspeed_FR', 0),
                    'wheel_speed_rl': electrics.get('wheelspeed_RL', 0),
                    'wheel_speed_rr': electrics.get('wheelspeed_RR', 0),
                    'steering_input': electrics.get('steering_input', 0),
                    'brake_input': electrics.get('brake_input', 0),
                    'throttle_input': electrics.get('throttle_input', 0),
                })

        self._raw_data = raw
        return {name: self._to_pycrash_df(records) for name, records in raw.items()}

    def _to_pycrash_df(self, records):
        """
        Convert raw BeamNG telemetry records to a pycrash-compatible DataFrame.

        Output columns match pycrash vehicle_model output:
            t, Dx, Dy, Vx, Vy, Vr, vx, vy, ax, ay, au, av,
            theta_deg, theta_rad, oz_deg, oz_rad, alphaz_deg, alphaz_rad
        """
        df = pd.DataFrame(records)

        if df.empty:
            return df

        # Time
        out = pd.DataFrame()
        out['t'] = df['t']

        # Position: BeamNG meters -> pycrash feet
        out['Dx'] = df['pos_x'] / FT_TO_M
        out['Dy'] = df['pos_y'] / FT_TO_M

        # Heading from quaternion
        heading_rad = 2 * np.arctan2(df['rot_z'], df['rot_w'])
        # BeamNG heading -> pycrash heading (CCW from X-axis)
        pycrash_heading_rad = np.pi / 2 - heading_rad
        out['theta_rad'] = pycrash_heading_rad
        out['theta_deg'] = np.degrees(pycrash_heading_rad)

        # World-frame velocity: m/s -> mph (for Vr), ft/s internally
        out['Vx'] = df['vel_x'] / FT_TO_M  # ft/s (pycrash world frame convention)
        out['Vy'] = df['vel_y'] / FT_TO_M
        out['Vr'] = np.sqrt(df['vel_x']**2 + df['vel_y']**2) / MPH_TO_MS  # mph

        # Vehicle-frame velocity
        cos_h = np.cos(pycrash_heading_rad)
        sin_h = np.sin(pycrash_heading_rad)
        out['vx'] = df['vel_x'] * cos_h + df['vel_y'] * sin_h  # forward (m/s -> ft/s)
        out['vx'] = out['vx'] / FT_TO_M
        out['vy'] = -df['vel_x'] * sin_h + df['vel_y'] * cos_h
        out['vy'] = out['vy'] / FT_TO_M

        # Yaw rate
        out['oz_rad'] = df['ang_vel_z']  # rad/s
        out['oz_deg'] = np.degrees(df['ang_vel_z'])

        # Accelerations via finite differences
        dt = df['t'].diff().fillna(df['t'].iloc[0] if len(df) > 0 else 0.01)
        dt = dt.replace(0, 0.01)

        out['ax'] = df['vel_x'].diff().fillna(0) / dt / FT_TO_M  # ft/s^2
        out['ay'] = df['vel_y'].diff().fillna(0) / dt / FT_TO_M

        # Vehicle-frame accelerations
        out['au'] = out['ax'] * cos_h + out['ay'] * sin_h
        out['av'] = -out['ax'] * sin_h + out['ay'] * cos_h

        # Yaw acceleration
        out['alphaz'] = df['ang_vel_z'].diff().fillna(0) / dt
        out['alphaz_deg'] = np.degrees(out['alphaz'])

        # Damage / deformation proxy
        out['damage'] = df['damage_total']

        # Driver inputs (normalized 0-1 in BeamNG)
        out['throttle'] = df['throttle_input']
        out['brake'] = df['brake_input']
        out['steer'] = df['steering_input']

        return out

    def get_crush_data(self, vehicle_name):
        """
        Extract crush/deformation data from BeamNG damage sensor.

        BeamNG's node-beam system provides deformation data that can be
        mapped to equivalent crush depth for comparison with pycrash's
        SDOF and stiffness models.

        Args:
            vehicle_name: Name of the vehicle to extract crush data for

        Returns:
            DataFrame with columns: t, damage_total, deform_groups
        """
        if vehicle_name not in self._raw_data:
            raise ValueError(f"No telemetry recorded for vehicle '{vehicle_name}'")

        records = self._raw_data[vehicle_name]
        crush = pd.DataFrame({
            't': [r['t'] for r in records],
            'damage_total': [r['damage_total'] for r in records],
            'deform_groups': [r['deform_group_damage'] for r in records],
        })

        return crush

    def get_delta_v(self, vehicle_name, impact_window=None):
        """
        Calculate delta-V from BeamNG telemetry during the impact event.

        Delta-V is the change in velocity during the collision, a critical
        metric in crash reconstruction.

        Args:
            vehicle_name: Vehicle name
            impact_window: (t_start, t_end) tuple in seconds. If None,
                          auto-detects the impact from deceleration spike.

        Returns:
            dict with delta_v_mph, delta_vx_mph, delta_vy_mph, impact_duration_s
        """
        if vehicle_name not in self._raw_data:
            raise ValueError(f"No telemetry recorded for vehicle '{vehicle_name}'")

        records = self._raw_data[vehicle_name]
        df = pd.DataFrame(records)

        if impact_window is None:
            # Auto-detect impact from velocity discontinuity
            vr = np.sqrt(df['vel_x']**2 + df['vel_y']**2)
            accel = np.abs(vr.diff().fillna(0)) / df['t'].diff().fillna(0.01)
            # Impact threshold: > 5g deceleration
            threshold = 5 * 9.81
            impact_mask = accel > threshold

            if not impact_mask.any():
                return {
                    'delta_v_mph': 0.0,
                    'delta_vx_mph': 0.0,
                    'delta_vy_mph': 0.0,
                    'impact_duration_s': 0.0,
                }

            impact_indices = impact_mask[impact_mask].index
            t_start_idx = max(0, impact_indices[0] - 1)
            t_end_idx = min(len(df) - 1, impact_indices[-1] + 1)
        else:
            t_start_idx = (df['t'] - impact_window[0]).abs().idxmin()
            t_end_idx = (df['t'] - impact_window[1]).abs().idxmin()

        dvx = df['vel_x'].iloc[t_end_idx] - df['vel_x'].iloc[t_start_idx]
        dvy = df['vel_y'].iloc[t_end_idx] - df['vel_y'].iloc[t_start_idx]
        dv = np.sqrt(dvx**2 + dvy**2)

        return {
            'delta_v_mph': float(dv / MPH_TO_MS),
            'delta_vx_mph': float(dvx / MPH_TO_MS),
            'delta_vy_mph': float(dvy / MPH_TO_MS),
            'impact_duration_s': float(
                df['t'].iloc[t_end_idx] - df['t'].iloc[t_start_idx]
            ),
        }
