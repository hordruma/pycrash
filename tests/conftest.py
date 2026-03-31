"""
Shared fixtures for pycrash test suite.

Provides realistic vehicle instances, driver inputs, and simulation defaults
used across multiple test modules.
"""
import pytest
import sys
import os
import pandas as pd
import numpy as np

# Ensure the pycrash package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# Vehicle input dictionaries
# ---------------------------------------------------------------------------

CAMRY_INPUT = {
    'year': 2020, 'make': 'Toyota', 'model': 'Camry',
    'weight': 3400, 'vin': 'TEST123',
    'brake': 0, 'steer_ratio': 16,
    'init_x_pos': 0, 'init_y_pos': 0, 'head_angle': 0,
    'width': 6.0, 'length': 16.0, 'hcg': 1.8,
    'lcgf': 4.5, 'lcgr': 5.0, 'wb': 9.5, 'track': 5.2,
    'f_hang': 3.0, 'r_hang': 3.5,
    'tire_d': 2.2, 'tire_w': 0.7,
    'izz': 2500, 'fwd': 1, 'rwd': 0, 'awd': 0,
    'A': 300, 'B': 150, 'k': 50000, 'L': 60, 'c': 12,
    'vx_initial': 30, 'vy_initial': 0, 'omega_z': 0,
    'striking': True,
}

CIVIC_INPUT = {
    'year': 2019, 'make': 'Honda', 'model': 'Civic',
    'weight': 2900, 'vin': 'TEST456',
    'brake': 0, 'steer_ratio': 15,
    'init_x_pos': 100, 'init_y_pos': 0, 'head_angle': 180,
    'width': 5.8, 'length': 15.0, 'hcg': 1.7,
    'lcgf': 4.2, 'lcgr': 4.8, 'wb': 9.0, 'track': 5.0,
    'f_hang': 2.8, 'r_hang': 3.2,
    'tire_d': 2.1, 'tire_w': 0.65,
    'izz': 2200, 'fwd': 1, 'rwd': 0, 'awd': 0,
    'A': 280, 'B': 140, 'k': 45000, 'L': 55, 'c': 10,
    'vx_initial': 0, 'vy_initial': 0, 'omega_z': 0,
    'striking': False,
}

TRUCK_RWD_INPUT = {
    'year': 2021, 'make': 'Ford', 'model': 'F150',
    'weight': 5000, 'vin': 'TESTTRK',
    'brake': 0, 'steer_ratio': 18,
    'init_x_pos': 0, 'init_y_pos': 0, 'head_angle': 0,
    'width': 6.8, 'length': 19.0, 'hcg': 2.4,
    'lcgf': 5.0, 'lcgr': 5.5, 'wb': 10.5, 'track': 5.6,
    'f_hang': 3.5, 'r_hang': 4.0,
    'tire_d': 2.6, 'tire_w': 0.85,
    'izz': 4000, 'fwd': 0, 'rwd': 1, 'awd': 0,
    'A': 350, 'B': 175, 'k': 60000, 'L': 70, 'c': 14,
    'vx_initial': 40, 'vy_initial': 0, 'omega_z': 0,
    'striking': True,
}

AWD_INPUT = {
    'year': 2022, 'make': 'Subaru', 'model': 'Outback',
    'weight': 3700, 'vin': 'TESTAWD',
    'brake': 0, 'steer_ratio': 14,
    'init_x_pos': 0, 'init_y_pos': 0, 'head_angle': 0,
    'width': 6.2, 'length': 16.5, 'hcg': 2.0,
    'lcgf': 4.6, 'lcgr': 5.1, 'wb': 9.7, 'track': 5.3,
    'f_hang': 3.1, 'r_hang': 3.4,
    'tire_d': 2.3, 'tire_w': 0.72,
    'izz': 2800, 'fwd': 0, 'rwd': 0, 'awd': 1,
    'A': 310, 'B': 155, 'k': 52000, 'L': 62, 'c': 11,
    'vx_initial': 35, 'vy_initial': 0, 'omega_z': 0,
    'striking': True,
}

SIM_DEFAULTS = {
    'dt_motion': 0.01,
    'mu_max': 0.8,
    'alpha_max': 0.174533,
}


# ---------------------------------------------------------------------------
# Helper: build a Vehicle without triggering plotly imports
# ---------------------------------------------------------------------------

def _make_vehicle(name, input_dict):
    """Create a Vehicle instance, patching out the plotly visualization import."""
    from pycrash.vehicle import Vehicle
    return Vehicle(name, input_dict=input_dict)


def _apply_driver_inputs(veh, time, throttle, brake, steer, dt_motion=0.01):
    """
    Apply driver inputs to a vehicle without triggering plotly plots.
    Reproduces the interpolation logic from Vehicle.time_inputs but skips
    the plot call.
    """
    inputdf = pd.DataFrame(list(zip(throttle, brake, steer)),
                           columns=['throttle', 'brake', 'steer'])
    t = list(np.arange(0, max(time) + dt_motion, dt_motion))
    t = [float(i) for i in t]
    df = pd.DataFrame()
    df['t'] = t
    inputdf['input_t'] = [float(num) for num in time]
    df.t = df.t.round(3).astype(float)
    df = pd.merge(df, inputdf, how='left', left_on='t', right_on='input_t')
    df = df.interpolate(method='linear', axis=0)
    df.drop(columns=['input_t', 't'], inplace=True)
    df['t'] = t
    df['t'] = df.t.round(3)
    df = df.reset_index(drop=True)
    veh.driver_input = df


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def camry_vehicle():
    """A Toyota Camry (FWD, 3400 lb, 30 mph initial)."""
    return _make_vehicle('Camry', CAMRY_INPUT)


@pytest.fixture
def civic_vehicle():
    """A Honda Civic (FWD, 2900 lb, stationary)."""
    return _make_vehicle('Civic', CIVIC_INPUT)


@pytest.fixture
def truck_rwd_vehicle():
    """A Ford F-150 (RWD, 5000 lb, 40 mph initial)."""
    return _make_vehicle('F150', TRUCK_RWD_INPUT)


@pytest.fixture
def awd_vehicle():
    """A Subaru Outback (AWD, 3700 lb, 35 mph initial)."""
    return _make_vehicle('Outback', AWD_INPUT)


@pytest.fixture
def camry_braking(camry_vehicle):
    """Camry with 100% braking applied for 3 seconds, no steering."""
    time = [0, 3]
    throttle = [0, 0]
    brake = [1, 1]
    steer = [0, 0]
    _apply_driver_inputs(camry_vehicle, time, throttle, brake, steer)
    return camry_vehicle


@pytest.fixture
def camry_coasting(camry_vehicle):
    """Camry coasting (no braking, no steering) for 3 seconds."""
    time = [0, 3]
    throttle = [0, 0]
    brake = [0, 0]
    steer = [0, 0]
    _apply_driver_inputs(camry_vehicle, time, throttle, brake, steer)
    return camry_vehicle


@pytest.fixture
def camry_turning(camry_vehicle):
    """Camry with steering input (90 degrees at wheel) for 3 seconds, no braking."""
    time = [0, 3]
    throttle = [0, 0]
    brake = [0, 0]
    steer = [90, 90]
    _apply_driver_inputs(camry_vehicle, time, throttle, brake, steer)
    return camry_vehicle


@pytest.fixture
def truck_braking(truck_rwd_vehicle):
    """F-150 RWD with 100% braking for 3 seconds."""
    time = [0, 3]
    throttle = [0, 0]
    brake = [1, 1]
    steer = [0, 0]
    _apply_driver_inputs(truck_rwd_vehicle, time, throttle, brake, steer)
    return truck_rwd_vehicle


@pytest.fixture
def awd_braking(awd_vehicle):
    """Subaru Outback AWD with 100% braking for 3 seconds."""
    time = [0, 3]
    throttle = [0, 0]
    brake = [1, 1]
    steer = [0, 0]
    _apply_driver_inputs(awd_vehicle, time, throttle, brake, steer)
    return awd_vehicle


@pytest.fixture
def sim_defaults():
    """Default simulation parameters."""
    return SIM_DEFAULTS.copy()
