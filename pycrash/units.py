"""
Unit conversion module for pycrash.

Pycrash uses imperial units internally (lb, ft, ft/s, mph, degrees).
This module provides conversion utilities so users can work in metric
(kg, m, m/s, km/h) and convert to/from imperial as needed.

All functions accept scalars and numpy arrays.
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
G_IMPERIAL = 32.2       # ft/s^2
G_METRIC = 9.81          # m/s^2

# ---------------------------------------------------------------------------
# Conversion factors (multiply source unit by factor to get target unit)
# ---------------------------------------------------------------------------
# Length
M_TO_FT = 3.28084
FT_TO_M = 0.3048
IN_TO_M = 0.0254
M_TO_IN = 1.0 / IN_TO_M  # 39.3701

# Speed
KMH_TO_MPH = 0.621371
MPH_TO_KMH = 1.0 / KMH_TO_MPH  # 1.60934
MPH_TO_FTS = 1.46667
FTS_TO_MPH = 1.0 / MPH_TO_FTS
MS_TO_FTS = M_TO_FT              # 3.28084
FTS_TO_MS = FT_TO_M              # 0.3048

# Mass / Weight
KG_TO_LB = 2.20462
LB_TO_KG = 1.0 / KG_TO_LB  # 0.453592

# Force
N_TO_LBF = 0.224809
LBF_TO_N = 4.44822

# Energy
J_TO_FTLB = 0.737562
FTLB_TO_J = 1.35582

# Angles
DEG_TO_RAD = np.pi / 180.0
RAD_TO_DEG = 180.0 / np.pi

# Stiffness
# lb/in -> N/m:  1 lb/in = 4.44822 N / 0.0254 m = 175.127 N/m
LBIN_TO_NM = LBF_TO_N / IN_TO_M
NM_TO_LBIN = 1.0 / LBIN_TO_NM

# lb/in/in -> N/m/m:  1 lb/in^2 = 4.44822 N / (0.0254 m)^2 = 6894.76 N/m^2
LBININ_TO_NMM = LBF_TO_N / (IN_TO_M ** 2)
NMM_TO_LBININ = 1.0 / LBININ_TO_NMM

# Moment of inertia: lb-ft-s^2 -> kg-m^2
# 1 lb-ft-s^2 = 1 slug-ft = (14.5939 kg)(0.3048 m)^2 * (1/0.3048) ... simplify:
# 1 lb-ft-s^2 = 1.35582 kg-m^2
LBFTS2_TO_KGM2 = FTLB_TO_J  # numerically identical: 1.35582
KGM2_TO_LBFTS2 = J_TO_FTLB  # 0.737562

# Acceleration
FTS2_TO_MS2 = FT_TO_M         # 0.3048
MS2_TO_FTS2 = M_TO_FT         # 3.28084


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------
def mph_to_kmh(v):
    """Convert speed from mph to km/h."""
    return np.asarray(v, dtype=float) * MPH_TO_KMH if not np.isscalar(v) else v * MPH_TO_KMH


def kmh_to_mph(v):
    """Convert speed from km/h to mph."""
    return np.asarray(v, dtype=float) * KMH_TO_MPH if not np.isscalar(v) else v * KMH_TO_MPH


def lb_to_kg(w):
    """Convert mass from lb to kg (treats input as mass in lb, not weight-force)."""
    return np.asarray(w, dtype=float) * LB_TO_KG if not np.isscalar(w) else w * LB_TO_KG


def kg_to_lb(m):
    """Convert mass from kg to lb."""
    return np.asarray(m, dtype=float) * KG_TO_LB if not np.isscalar(m) else m * KG_TO_LB


def ft_to_m(d):
    """Convert length from ft to m."""
    return np.asarray(d, dtype=float) * FT_TO_M if not np.isscalar(d) else d * FT_TO_M


def m_to_ft(d):
    """Convert length from m to ft."""
    return np.asarray(d, dtype=float) * M_TO_FT if not np.isscalar(d) else d * M_TO_FT


def lbf_to_n(f):
    """Convert force from lb (lbf) to Newtons."""
    return np.asarray(f, dtype=float) * LBF_TO_N if not np.isscalar(f) else f * LBF_TO_N


def n_to_lbf(f):
    """Convert force from Newtons to lb (lbf)."""
    return np.asarray(f, dtype=float) * N_TO_LBF if not np.isscalar(f) else f * N_TO_LBF


def ftlb_to_j(e):
    """Convert energy from ft-lb to Joules."""
    return np.asarray(e, dtype=float) * FTLB_TO_J if not np.isscalar(e) else e * FTLB_TO_J


def j_to_ftlb(e):
    """Convert energy from Joules to ft-lb."""
    return np.asarray(e, dtype=float) * J_TO_FTLB if not np.isscalar(e) else e * J_TO_FTLB


def deg_to_rad(a):
    """Convert angle from degrees to radians."""
    return np.asarray(a, dtype=float) * DEG_TO_RAD if not np.isscalar(a) else a * DEG_TO_RAD


def rad_to_deg(a):
    """Convert angle from radians to degrees."""
    return np.asarray(a, dtype=float) * RAD_TO_DEG if not np.isscalar(a) else a * RAD_TO_DEG


def ms_to_fts(v):
    """Convert speed from m/s to ft/s."""
    return np.asarray(v, dtype=float) * MS_TO_FTS if not np.isscalar(v) else v * MS_TO_FTS


def fts_to_ms(v):
    """Convert speed from ft/s to m/s."""
    return np.asarray(v, dtype=float) * FTS_TO_MS if not np.isscalar(v) else v * FTS_TO_MS


def kmh_to_ms(v):
    """Convert speed from km/h to m/s."""
    return np.asarray(v, dtype=float) / 3.6 if not np.isscalar(v) else v / 3.6


def ms_to_kmh(v):
    """Convert speed from m/s to km/h."""
    return np.asarray(v, dtype=float) * 3.6 if not np.isscalar(v) else v * 3.6


# ---------------------------------------------------------------------------
# MetricVehicle - convert a metric vehicle property dict to imperial
# ---------------------------------------------------------------------------
def MetricVehicle(metric_dict):
    """
    Convert a dictionary of vehicle properties in metric units to imperial
    units suitable for passing to ``Vehicle(name, input_dict=converted)``.

    Metric input keys and their conversions:

        mass_kg          -> weight (lb)           mass * g_imperial / g_metric * kg_to_lb
                           (weight = mass * g, but pycrash 'weight' is in lb-force,
                            so weight_lb = mass_kg * g_metric * N_TO_LBF ... which
                            simplifies to mass_kg * KG_TO_LB * 1.0 since 1 kg weighs
                            2.20462 lb on Earth. The exact conversion:
                            weight_lb = mass_kg * 9.81 * 0.224809 = mass_kg * 2.20462)
        width_m          -> width (ft)
        length_m         -> length (ft)
        hcg_m            -> hcg (ft)
        lcgf_m           -> lcgf (ft)
        lcgr_m           -> lcgr (ft)
        wb_m             -> wb (ft)
        track_m          -> track (ft)
        f_hang_m         -> f_hang (ft)
        r_hang_m         -> r_hang (ft)
        tire_d_m         -> tire_d (ft)
        tire_w_m         -> tire_w (ft)
        vx_initial_kmh   -> vx_initial (mph)
        vy_initial_kmh   -> vy_initial (mph)
        izz_kgm2         -> izz (lb-ft-s^2)
        A_Nm             -> A (lb/in)
        B_Nm_m           -> B (lb/in/in)
        k_Nm             -> k (lb/ft)
        L_m              -> L (in)
        c_m              -> c (in)

    Keys not listed above are passed through unchanged (e.g. year, make,
    model, vin, fwd, rwd, awd, brake, steer_ratio, head_angle, omega_z,
    striking, notes, init_x_pos, init_y_pos).

    Parameters
    ----------
    metric_dict : dict
        Vehicle properties in metric units.

    Returns
    -------
    dict
        Vehicle properties in imperial units ready for pycrash Vehicle().
    """
    imperial = {}

    # Mapping: (metric_key, imperial_key, conversion_function)
    length_m_keys = {
        'width_m': 'width',
        'length_m': 'length',
        'hcg_m': 'hcg',
        'lcgf_m': 'lcgf',
        'lcgr_m': 'lcgr',
        'wb_m': 'wb',
        'track_m': 'track',
        'f_hang_m': 'f_hang',
        'r_hang_m': 'r_hang',
        'tire_d_m': 'tire_d',
        'tire_w_m': 'tire_w',
    }

    speed_kmh_keys = {
        'vx_initial_kmh': 'vx_initial',
        'vy_initial_kmh': 'vy_initial',
    }

    length_m_to_in_keys = {
        'L_m': 'L',
        'c_m': 'c',
    }

    for key, value in metric_dict.items():
        if key == 'mass_kg':
            # weight in lb = mass_kg * g_metric (N) * N_TO_LBF = mass_kg * KG_TO_LB
            imperial['weight'] = value * KG_TO_LB
        elif key in length_m_keys:
            imperial[length_m_keys[key]] = value * M_TO_FT
        elif key in speed_kmh_keys:
            imperial[speed_kmh_keys[key]] = value * KMH_TO_MPH
        elif key == 'izz_kgm2':
            imperial['izz'] = value * KGM2_TO_LBFTS2
        elif key == 'A_Nm':
            # A is in lb/in in pycrash; input is N/m
            imperial['A'] = value * NM_TO_LBIN
        elif key == 'B_Nm_m':
            # B is in lb/in/in in pycrash; input is N/m/m
            imperial['B'] = value * NMM_TO_LBININ
        elif key == 'k_Nm':
            # k is in lb/ft in pycrash; input is N/m
            # 1 N/m = 0.224809 lb / 3.28084 ft = 0.068522 lb/ft
            imperial['k'] = value * N_TO_LBF / M_TO_FT
        elif key in length_m_to_in_keys:
            imperial[length_m_to_in_keys[key]] = value * M_TO_IN
        else:
            # Pass through unchanged (year, make, model, etc.)
            imperial[key] = value

    return imperial


# ---------------------------------------------------------------------------
# MetricResults - convert a vehicle.model DataFrame to metric units
# ---------------------------------------------------------------------------
def MetricResults(model_df):
    """
    Convert a pycrash ``vehicle.model`` DataFrame from imperial to metric
    units and return a copy.

    Conversion rules applied by column name pattern:

    - **Velocities** (ft/s -> m/s): columns matching ``vx, vy, Vx, Vy, Vr``
    - **Speeds** (mph -> km/h): columns ending with ``_mph`` if any exist
    - **Accelerations** (ft/s^2 -> m/s^2): columns matching ``au, av, Ax, Ay, Ar``
      (g-based columns like ``ax_g`` are left unchanged)
    - **Forces** (lb -> N): columns matching ``_fx, _fy, _fz, Fx, Fy, Mz``
      Note: Mz is moment (lb-ft -> N-m) so gets its own factor
    - **Distances** (ft -> m): columns matching ``Dx, Dy``
    - **Angles**: left unchanged (radians/degrees are unit-system agnostic)
    - **Time**: left unchanged

    Parameters
    ----------
    model_df : pandas.DataFrame
        The ``vehicle.model`` DataFrame in imperial units.

    Returns
    -------
    pandas.DataFrame
        A copy of the DataFrame with metric units.
    """
    df = model_df.copy()

    # Velocity columns (ft/s -> m/s)
    velocity_cols = ['vx', 'vy', 'Vx', 'Vy', 'Vr']
    for col in velocity_cols:
        if col in df.columns:
            df[col] = df[col] * FTS_TO_MS

    # Acceleration columns (ft/s^2 -> m/s^2)
    accel_cols = ['au', 'av', 'Ax', 'Ay', 'Ar']
    for col in accel_cols:
        if col in df.columns:
            df[col] = df[col] * FTS2_TO_MS2

    # Force columns (lb -> N): tire forces and resultant forces
    # Pattern: lf_fx, lf_fy, rf_fx, rf_fy, rr_fx, rr_fy, lr_fx, lr_fy
    #          lf_fz, rf_fz, rr_fz, lr_fz, Fx, Fy
    force_exact = ['Fx', 'Fy']
    force_suffixes = ('_fx', '_fy', '_fz')
    for col in df.columns:
        if col in force_exact:
            df[col] = df[col] * LBF_TO_N
        elif any(col.endswith(s) for s in force_suffixes):
            df[col] = df[col] * LBF_TO_N

    # Moment column (lb-ft -> N-m)
    if 'Mz' in df.columns:
        df['Mz'] = df['Mz'] * LBF_TO_N * FT_TO_M

    # Distance columns (ft -> m)
    distance_cols = ['Dx', 'Dy']
    for col in distance_cols:
        if col in df.columns:
            df[col] = df[col] * FT_TO_M

    return df
