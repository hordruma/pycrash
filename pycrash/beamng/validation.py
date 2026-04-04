"""
Compares pycrash analytical reconstruction results with BeamNG.tech simulation
telemetry for validation and analysis.

Provides quantitative metrics and visualization for assessing how well the
2D analytical model matches the 3D soft-body simulation.
"""

import numpy as np
import pandas as pd


class ValidationComparator:
    """
    Compares pycrash analytical results with BeamNG telemetry data.

    Metrics computed:
    - Trajectory deviation (RMS position error over time)
    - Velocity profile comparison
    - Delta-V comparison (analytical vs simulated)
    - Rest position error
    - Heading angle deviation
    - Energy dissipation comparison
    """

    def __init__(self, pycrash_df, beamng_df, vehicle_name="Vehicle"):
        """
        Args:
            pycrash_df: DataFrame from pycrash simulation (vehicle_model output)
            beamng_df: DataFrame from TelemetryExtractor (pycrash-compatible format)
            vehicle_name: Label for reports and plots
        """
        self.pycrash_df = pycrash_df.copy()
        self.beamng_df = beamng_df.copy()
        self.vehicle_name = vehicle_name
        self._aligned = False
        self._align_data()

    def _align_data(self):
        """
        Align pycrash and BeamNG DataFrames to common time steps via interpolation.
        """
        # Use the coarser time grid (typically pycrash at 0.01-0.1s)
        t_min = max(self.pycrash_df['t'].iloc[0], self.beamng_df['t'].iloc[0])
        t_max = min(self.pycrash_df['t'].iloc[-1], self.beamng_df['t'].iloc[-1])

        if t_max <= t_min:
            self._aligned = False
            return

        # Use pycrash time steps as the reference grid
        mask = (self.pycrash_df['t'] >= t_min) & (self.pycrash_df['t'] <= t_max)
        t_common = self.pycrash_df.loc[mask, 't'].values

        # Interpolate BeamNG data to match pycrash time steps
        interp_cols = ['Dx', 'Dy', 'Vx', 'Vy', 'Vr', 'theta_deg', 'oz_deg']
        bng_interp = {}
        for col in interp_cols:
            if col in self.beamng_df.columns:
                bng_interp[col] = np.interp(
                    t_common,
                    self.beamng_df['t'].values,
                    self.beamng_df[col].values
                )

        self._t_common = t_common
        self._pc_aligned = self.pycrash_df.loc[mask].reset_index(drop=True)
        self._bng_aligned = pd.DataFrame({'t': t_common, **bng_interp})
        self._aligned = True

    def trajectory_error(self):
        """
        Compute trajectory deviation between pycrash and BeamNG.

        Returns:
            dict with:
                rms_position_ft: RMS position error in feet
                max_position_ft: Maximum position error in feet
                rms_heading_deg: RMS heading error in degrees
                final_position_error_ft: Error at simulation end
                errors_df: DataFrame with per-timestep errors
        """
        if not self._aligned:
            return {'error': 'DataFrames could not be aligned (no time overlap)'}

        pc = self._pc_aligned
        bng = self._bng_aligned

        dx = pc['Dx'].values - bng['Dx'].values
        dy = pc['Dy'].values - bng['Dy'].values
        pos_err = np.sqrt(dx**2 + dy**2)

        heading_err = np.abs(pc['theta_deg'].values - bng['theta_deg'].values)
        # Handle angle wrapping
        heading_err = np.minimum(heading_err, 360 - heading_err)

        errors = pd.DataFrame({
            't': self._t_common,
            'position_error_ft': pos_err,
            'heading_error_deg': heading_err,
            'dx_error_ft': dx,
            'dy_error_ft': dy,
        })

        return {
            'rms_position_ft': float(np.sqrt(np.mean(pos_err**2))),
            'max_position_ft': float(np.max(pos_err)),
            'rms_heading_deg': float(np.sqrt(np.mean(heading_err**2))),
            'final_position_error_ft': float(pos_err[-1]) if len(pos_err) > 0 else 0,
            'errors_df': errors,
        }

    def velocity_comparison(self):
        """
        Compare velocity profiles between pycrash and BeamNG.

        Returns:
            dict with RMS speed error, peak speed difference, and comparison DataFrame
        """
        if not self._aligned:
            return {'error': 'DataFrames could not be aligned'}

        pc = self._pc_aligned
        bng = self._bng_aligned

        speed_err = pc['Vr'].values - bng['Vr'].values

        comparison = pd.DataFrame({
            't': self._t_common,
            'pycrash_speed_mph': pc['Vr'].values,
            'beamng_speed_mph': bng['Vr'].values,
            'speed_diff_mph': speed_err,
        })

        return {
            'rms_speed_error_mph': float(np.sqrt(np.mean(speed_err**2))),
            'max_speed_error_mph': float(np.max(np.abs(speed_err))),
            'comparison_df': comparison,
        }

    def delta_v_comparison(self, pycrash_delta_v, beamng_delta_v):
        """
        Compare delta-V values from pycrash IMPC/SDOF with BeamNG telemetry.

        Args:
            pycrash_delta_v: dict with delta_v_mph from pycrash model
            beamng_delta_v: dict from TelemetryExtractor.get_delta_v()

        Returns:
            dict with absolute and percent differences
        """
        pc_dv = pycrash_delta_v.get('delta_v_mph', 0)
        bng_dv = beamng_delta_v.get('delta_v_mph', 0)

        diff = abs(pc_dv - bng_dv)
        pct_diff = (diff / pc_dv * 100) if pc_dv != 0 else float('inf')

        return {
            'pycrash_delta_v_mph': pc_dv,
            'beamng_delta_v_mph': bng_dv,
            'absolute_diff_mph': diff,
            'percent_diff': pct_diff,
            'pycrash_duration_s': pycrash_delta_v.get('impact_duration_s', 0),
            'beamng_duration_s': beamng_delta_v.get('impact_duration_s', 0),
        }

    def summary_report(self):
        """
        Generate a comprehensive validation summary.

        Returns:
            dict with all comparison metrics and a text summary
        """
        traj = self.trajectory_error()
        vel = self.velocity_comparison()

        if 'error' in traj:
            return {'error': traj['error']}

        report = {
            'vehicle': self.vehicle_name,
            'duration_s': float(self._t_common[-1] - self._t_common[0]),
            'trajectory': {
                'rms_position_ft': traj['rms_position_ft'],
                'max_position_ft': traj['max_position_ft'],
                'rms_heading_deg': traj['rms_heading_deg'],
                'final_position_error_ft': traj['final_position_error_ft'],
            },
            'velocity': {
                'rms_speed_error_mph': vel['rms_speed_error_mph'],
                'max_speed_error_mph': vel['max_speed_error_mph'],
            },
        }

        # Text summary
        lines = [
            f"=== Validation Report: {self.vehicle_name} ===",
            f"Duration: {report['duration_s']:.2f} s",
            f"",
            f"Trajectory:",
            f"  RMS position error:   {traj['rms_position_ft']:.2f} ft",
            f"  Max position error:   {traj['max_position_ft']:.2f} ft",
            f"  Final position error: {traj['final_position_error_ft']:.2f} ft",
            f"  RMS heading error:    {traj['rms_heading_deg']:.2f} deg",
            f"",
            f"Velocity:",
            f"  RMS speed error: {vel['rms_speed_error_mph']:.2f} mph",
            f"  Max speed error: {vel['max_speed_error_mph']:.2f} mph",
        ]
        report['text'] = '\n'.join(lines)

        return report

    def plot_comparison(self):
        """
        Create interactive Plotly comparison plots.

        Returns:
            dict of plotly Figure objects:
                'trajectory': XY path overlay
                'speed': Speed vs time overlay
                'heading': Heading vs time overlay
                'errors': Error vs time plots
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            raise ImportError("plotly is required for visualization")

        if not self._aligned:
            raise ValueError("Data could not be aligned for comparison")

        pc = self._pc_aligned
        bng = self._bng_aligned
        t = self._t_common

        figures = {}

        # Trajectory comparison
        fig_traj = go.Figure()
        fig_traj.add_trace(go.Scatter(
            x=pc['Dx'], y=pc['Dy'], mode='lines',
            name='pycrash (analytical)', line=dict(color='blue')
        ))
        fig_traj.add_trace(go.Scatter(
            x=bng['Dx'], y=bng['Dy'], mode='lines',
            name='BeamNG (simulation)', line=dict(color='red', dash='dash')
        ))
        fig_traj.update_layout(
            title=f'{self.vehicle_name} - Trajectory Comparison',
            xaxis_title='X Position (ft)', yaxis_title='Y Position (ft)',
            yaxis_scaleanchor='x',
        )
        figures['trajectory'] = fig_traj

        # Speed comparison
        fig_speed = go.Figure()
        fig_speed.add_trace(go.Scatter(
            x=t, y=pc['Vr'], mode='lines',
            name='pycrash', line=dict(color='blue')
        ))
        fig_speed.add_trace(go.Scatter(
            x=t, y=bng['Vr'], mode='lines',
            name='BeamNG', line=dict(color='red', dash='dash')
        ))
        fig_speed.update_layout(
            title=f'{self.vehicle_name} - Speed Comparison',
            xaxis_title='Time (s)', yaxis_title='Speed (mph)',
        )
        figures['speed'] = fig_speed

        # Heading comparison
        fig_head = go.Figure()
        fig_head.add_trace(go.Scatter(
            x=t, y=pc['theta_deg'], mode='lines',
            name='pycrash', line=dict(color='blue')
        ))
        fig_head.add_trace(go.Scatter(
            x=t, y=bng['theta_deg'], mode='lines',
            name='BeamNG', line=dict(color='red', dash='dash')
        ))
        fig_head.update_layout(
            title=f'{self.vehicle_name} - Heading Comparison',
            xaxis_title='Time (s)', yaxis_title='Heading (deg)',
        )
        figures['heading'] = fig_head

        # Error plots
        traj_err = self.trajectory_error()
        err_df = traj_err['errors_df']

        fig_err = make_subplots(rows=2, cols=1,
                                subplot_titles=['Position Error', 'Heading Error'])
        fig_err.add_trace(go.Scatter(
            x=err_df['t'], y=err_df['position_error_ft'],
            mode='lines', name='Position Error (ft)', line=dict(color='purple')
        ), row=1, col=1)
        fig_err.add_trace(go.Scatter(
            x=err_df['t'], y=err_df['heading_error_deg'],
            mode='lines', name='Heading Error (deg)', line=dict(color='orange')
        ), row=2, col=1)
        fig_err.update_layout(title=f'{self.vehicle_name} - Validation Errors')
        figures['errors'] = fig_err

        return figures
