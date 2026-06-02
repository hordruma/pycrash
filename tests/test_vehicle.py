"""
Tests for pycrash/vehicle.py -- Vehicle class.

Tests cover:
  - Vehicle creation with input dictionary
  - Property assignment and type casting
  - Driver input application and interpolation
"""
import pytest
import pandas as pd
import numpy as np

from pycrash.vehicle import Vehicle

from tests.conftest import CAMRY_INPUT, CIVIC_INPUT, TRUCK_RWD_INPUT, AWD_INPUT, _apply_driver_inputs


# ============================================================================
# Vehicle creation
# ============================================================================

class TestVehicleCreation:

    def test_create_with_name_only(self):
        """Vehicle can be created with just a name."""
        veh = Vehicle('TestVeh')
        assert veh.name == 'TestVeh'
        assert veh.type == 'vehicle'

    def test_create_with_input_dict(self):
        """Vehicle created with input_dict should have all attributes set."""
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert veh.name == 'Camry'
        assert veh.weight == pytest.approx(3400)
        assert veh.wb == pytest.approx(9.5)
        assert veh.vx_initial == pytest.approx(30)

    def test_string_fields_stored_as_string(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert isinstance(veh.make, str)
        assert isinstance(veh.model, str)
        assert isinstance(veh.vin, str)
        assert veh.make == 'Toyota'

    def test_numeric_fields_stored_as_float(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert isinstance(veh.weight, float)
        assert isinstance(veh.wb, float)
        assert isinstance(veh.hcg, float)

    def test_drivetrain_fields_stored_as_bool(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert isinstance(veh.fwd, bool)
        assert isinstance(veh.rwd, bool)
        assert isinstance(veh.awd, bool)
        assert veh.fwd is True
        assert veh.rwd is False
        assert veh.awd is False

    def test_rwd_vehicle(self):
        veh = Vehicle('F150', input_dict=TRUCK_RWD_INPUT)
        assert veh.fwd is False
        assert veh.rwd is True
        assert veh.awd is False

    def test_awd_vehicle(self):
        veh = Vehicle('Outback', input_dict=AWD_INPUT)
        assert veh.fwd is False
        assert veh.rwd is False
        assert veh.awd is True


# ============================================================================
# Vehicle properties
# ============================================================================

class TestVehicleProperties:

    def test_wheelbase_equals_lcgf_plus_lcgr(self):
        """Wheelbase should equal lcgf + lcgr."""
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert veh.wb == pytest.approx(veh.lcgf + veh.lcgr, rel=1e-3)

    def test_stiffness_values(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert veh.A == pytest.approx(300)
        assert veh.B == pytest.approx(150)
        assert veh.k == pytest.approx(50000)

    def test_initial_velocity(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert veh.vx_initial == pytest.approx(30)
        assert veh.vy_initial == pytest.approx(0)

    def test_initial_position(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        assert veh.init_x_pos == pytest.approx(0)
        assert veh.init_y_pos == pytest.approx(0)

    def test_head_angle(self):
        veh = Vehicle('Civic', input_dict=CIVIC_INPUT)
        assert veh.head_angle == pytest.approx(180)


# ============================================================================
# Driver inputs
# ============================================================================

class TestDriverInputs:

    def test_driver_input_creates_dataframe(self):
        """time_inputs should create a driver_input DataFrame."""
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 3], [0, 0], [1, 1], [0, 0])
        assert hasattr(veh, 'driver_input')
        assert isinstance(veh.driver_input, pd.DataFrame)

    def test_driver_input_columns(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 3], [0, 0], [1, 1], [0, 0])
        assert 'throttle' in veh.driver_input.columns
        assert 'brake' in veh.driver_input.columns
        assert 'steer' in veh.driver_input.columns
        assert 't' in veh.driver_input.columns

    def test_driver_input_time_step(self):
        """Time column should increment by dt_motion (0.01s)."""
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 1], [0, 0], [0, 0], [0, 0], dt_motion=0.01)
        dt = veh.driver_input.t.diff().dropna()
        assert np.allclose(dt.values, 0.01, atol=0.001)

    def test_constant_brake_input(self):
        """Constant 100% braking should produce all 1s in brake column."""
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 2], [0, 0], [1, 1], [0, 0])
        assert np.allclose(veh.driver_input.brake.values, 1.0, atol=0.01)

    def test_interpolated_brake_ramp(self):
        """Braking ramping from 0 to 1 should be linearly interpolated."""
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 1], [0, 0], [0, 1], [0, 0])
        # At t=0.5, brake should be ~0.5
        mid_idx = len(veh.driver_input) // 2
        assert veh.driver_input.brake.iloc[mid_idx] == pytest.approx(0.5, abs=0.02)

    def test_steering_input(self):
        """Constant steering should produce uniform steer values."""
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 2], [0, 0], [0, 0], [90, 90])
        assert np.allclose(veh.driver_input.steer.values, 90, atol=0.1)

    def test_zero_throttle_default(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 2], [0, 0], [0, 0], [0, 0])
        assert np.allclose(veh.driver_input.throttle.values, 0, atol=0.01)

    def test_driver_input_starts_at_zero(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        _apply_driver_inputs(veh, [0, 2], [0, 0], [1, 1], [0, 0])
        assert veh.driver_input.t.iloc[0] == pytest.approx(0, abs=0.001)


# ============================================================================
# Vehicle show method
# ============================================================================

class TestVehicleShow:

    def test_show_does_not_raise(self):
        veh = Vehicle('Camry', input_dict=CAMRY_INPUT)
        # Should not raise any exception
        veh.show()
