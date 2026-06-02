"""
Tests for pycrash/model_calcs/tire_model.py -- tire force calculations.

The tire_forces function modifies a Vehicle object in-place. We test it by
creating minimal vehicle objects with the required DataFrame and attributes,
then calling tire_forces() and checking the results.
"""
import pytest
import math
import numpy as np
import pandas as pd

from pycrash.model_calcs.tire_model import tire_forces, sign as tire_sign
from pycrash.vehicle_model import column_list


# ---------------------------------------------------------------------------
# Helpers to build minimal vehicle objects for tire_forces
# ---------------------------------------------------------------------------

class SimpleVehicle:
    """Minimal vehicle-like object with attributes needed by tire_forces."""
    pass


def make_vehicle(weight=3400, wb=9.5, lcgf=4.5, lcgr=5.0, track=5.2,
                 hcg=1.8, steer_ratio=16, fwd=1, rwd=0, awd=0,
                 vx=44.0, vy=0, oz_rad=0, n_steps=1):
    """
    Create a SimpleVehicle with a model DataFrame and driver_input DataFrame.
    vx, vy in ft/s.  oz_rad in rad/s.
    """
    veh = SimpleVehicle()
    veh.weight = weight
    veh.wb = wb
    veh.lcgf = lcgf
    veh.lcgr = lcgr
    veh.track = track
    veh.hcg = hcg
    veh.steer_ratio = steer_ratio
    veh.fwd = fwd
    veh.rwd = rwd
    veh.awd = awd

    # model DataFrame
    veh.model = pd.DataFrame(np.nan, index=np.arange(n_steps), columns=column_list)
    veh.model.vx[0] = vx
    veh.model.vy[0] = vy
    veh.model.oz_rad[0] = oz_rad
    veh.model.au[0] = 0
    veh.model.av[0] = 0
    veh.model.theta_rad[0] = 0

    # driver_input DataFrame
    veh.driver_input = pd.DataFrame({
        't': [0.0] * n_steps,
        'throttle': [0.0] * n_steps,
        'brake': [0.0] * n_steps,
        'steer': [0.0] * n_steps,
    })

    return veh


# ---------------------------------------------------------------------------
# sign() helper
# ---------------------------------------------------------------------------

class TestTireSign:
    def test_positive(self):
        assert tire_sign(5) == 1

    def test_negative(self):
        assert tire_sign(-3) == -1

    def test_zero(self):
        assert tire_sign(0) == 0


# ---------------------------------------------------------------------------
# Static weight distribution (no acceleration)
# ---------------------------------------------------------------------------

class TestStaticWeightDistribution:
    """With no acceleration, tire loads should equal static weight distribution."""

    def test_total_vertical_force_equals_weight(self):
        """Sum of all four tire Fz should equal vehicle weight."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle()
        veh = tire_forces(veh, 0, sim_defaults)

        total_fz = (veh.model.lf_fz[0] + veh.model.rf_fz[0] +
                    veh.model.rr_fz[0] + veh.model.lr_fz[0])
        assert total_fz == pytest.approx(veh.weight, rel=1e-3)

    def test_left_right_symmetry(self):
        """With no lateral accel (av=0), left and right should be symmetric."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle()
        veh = tire_forces(veh, 0, sim_defaults)

        assert veh.model.lf_fz[0] == pytest.approx(veh.model.rf_fz[0], rel=1e-3)
        assert veh.model.lr_fz[0] == pytest.approx(veh.model.rr_fz[0], rel=1e-3)

    def test_front_rear_weight_split(self):
        """Static front/rear split based on CG location."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(weight=3400, wb=9.5, lcgf=4.5, lcgr=5.0)
        veh = tire_forces(veh, 0, sim_defaults)

        # Front axle should carry lcgr/wb fraction of weight
        expected_front = 3400 * 5.0 / 9.5
        actual_front = veh.model.lf_fz[0] + veh.model.rf_fz[0]
        assert actual_front == pytest.approx(expected_front, rel=1e-3)


# ---------------------------------------------------------------------------
# Braking forces
# ---------------------------------------------------------------------------

class TestBraking:

    def test_fwd_full_braking_all_tires_produce_force(self):
        """FWD with 100% braking: all 4 tires should produce braking force."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(fwd=1, rwd=0, awd=0, vx=44.0)
        veh.driver_input.brake[0] = 1.0
        veh = tire_forces(veh, 0, sim_defaults)

        # All tire fx should be negative (opposing forward motion)
        assert veh.model.lf_fx[0] < 0
        assert veh.model.rf_fx[0] < 0
        assert veh.model.rr_fx[0] < 0
        assert veh.model.lr_fx[0] < 0

    def test_rwd_full_braking_all_tires_produce_force(self):
        """RWD with 100% braking: all tires should brake."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(fwd=0, rwd=1, awd=0, vx=44.0)
        veh.driver_input.brake[0] = 1.0
        veh = tire_forces(veh, 0, sim_defaults)

        assert veh.model.lf_fx[0] < 0
        assert veh.model.rf_fx[0] < 0
        assert veh.model.rr_fx[0] < 0
        assert veh.model.lr_fx[0] < 0

    def test_awd_full_braking_all_tires_produce_force(self):
        """AWD with 100% braking: all tires should brake."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(fwd=0, rwd=0, awd=1, vx=44.0)
        veh.driver_input.brake[0] = 1.0
        veh = tire_forces(veh, 0, sim_defaults)

        # all tires should produce braking force (negative fx)
        assert veh.model.lf_fx[0] < 0
        assert veh.model.rf_fx[0] < 0
        assert veh.model.rr_fx[0] < 0
        assert veh.model.lr_fx[0] < 0

    def test_total_braking_force_limited_by_friction(self):
        """Total braking force should not exceed mu * weight."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(weight=3400, vx=44.0)
        veh.driver_input.brake[0] = 1.0
        veh = tire_forces(veh, 0, sim_defaults)

        total_fx = abs(veh.model.lf_fx[0] + veh.model.rf_fx[0] +
                       veh.model.rr_fx[0] + veh.model.lr_fx[0])
        max_friction = 0.8 * 3400
        assert total_fx <= max_friction * 1.01  # small tolerance

    def test_no_braking_no_force(self):
        """No braking and no steering should produce minimal tire forces."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(vx=44.0)
        veh = tire_forces(veh, 0, sim_defaults)

        # No brake, no throttle, no steer => very small forces
        total_fx = abs(veh.model.lf_fx[0] + veh.model.rf_fx[0] +
                       veh.model.rr_fx[0] + veh.model.lr_fx[0])
        assert total_fx == pytest.approx(0, abs=1.0)


# ---------------------------------------------------------------------------
# Tire lock detection
# ---------------------------------------------------------------------------

class TestTireLock:

    def test_full_braking_at_straight_ahead_boundary(self):
        """100% braking at straight-ahead with zero slip angle:
        applied force exactly equals mu*Fz (the model uses strict '>'),
        so tires stay at the lock boundary but lock flag is 0.
        This is a known edge case in the tire model."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(vx=44.0)
        veh.driver_input.brake[0] = 1.0
        veh = tire_forces(veh, 0, sim_defaults)

        # At exactly 100% braking with zero alpha, force equals limit.
        # The model uses strict '>' so lock=0 at the boundary.
        assert veh.model.lf_lock[0] == 0
        assert veh.model.rf_lock[0] == 0
        assert veh.model.rr_lock[0] == 0
        assert veh.model.lr_lock[0] == 0

    def test_braking_with_yaw_causes_lock(self):
        """Braking with some yaw rate produces slip angle, combined force
        exceeds friction limit, causing tire lock."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(vx=44.0, oz_rad=0.3)  # yaw rate creates slip angles
        veh.driver_input.brake[0] = 1.0
        veh = tire_forces(veh, 0, sim_defaults)

        # At least some tires should lock due to combined force exceeding limit
        locks = [veh.model.lf_lock[0], veh.model.rf_lock[0],
                 veh.model.rr_lock[0], veh.model.lr_lock[0]]
        assert any(lock == 1 for lock in locks)

    def test_no_braking_no_lock(self):
        """No braking should not lock tires."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(vx=44.0)
        veh = tire_forces(veh, 0, sim_defaults)

        assert veh.model.lf_lock[0] == 0
        assert veh.model.rf_lock[0] == 0
        assert veh.model.rr_lock[0] == 0
        assert veh.model.lr_lock[0] == 0


# ---------------------------------------------------------------------------
# Steering / slip angle
# ---------------------------------------------------------------------------

class TestSteering:

    def test_zero_steer_zero_delta(self):
        """No steering input -> delta = 0."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(steer_ratio=16)
        veh = tire_forces(veh, 0, sim_defaults)
        assert veh.model.delta_deg[0] == pytest.approx(0, abs=1e-6)
        assert veh.model.delta_rad[0] == pytest.approx(0, abs=1e-6)

    def test_positive_steer_produces_positive_delta(self):
        """Positive steering wheel angle -> positive delta (left turn)."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(steer_ratio=16, vx=44.0)
        veh.driver_input.steer[0] = 90  # 90 degrees at wheel
        veh = tire_forces(veh, 0, sim_defaults)
        assert veh.model.delta_deg[0] == pytest.approx(90 / 16, rel=1e-3)
        assert veh.model.delta_rad[0] > 0

    def test_steering_produces_lateral_force(self):
        """Steering should produce lateral tire forces (fy)."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(vx=44.0)
        veh.driver_input.steer[0] = 90
        veh = tire_forces(veh, 0, sim_defaults)

        # Front tires should have lateral forces
        total_fy = abs(veh.model.lf_fy[0]) + abs(veh.model.rf_fy[0])
        assert total_fy > 0

    def test_slip_angle_straight_ahead_near_zero(self):
        """Straight-ahead driving should produce near-zero slip angles."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(vx=44.0, vy=0, oz_rad=0)
        veh = tire_forces(veh, 0, sim_defaults)

        assert veh.model.lf_alpha[0] == pytest.approx(0, abs=0.01)
        assert veh.model.rf_alpha[0] == pytest.approx(0, abs=0.01)
        assert veh.model.rr_alpha[0] == pytest.approx(0, abs=0.01)
        assert veh.model.lr_alpha[0] == pytest.approx(0, abs=0.01)


# ---------------------------------------------------------------------------
# Weight transfer under braking
# ---------------------------------------------------------------------------

class TestWeightTransfer:

    def test_braking_increases_front_load(self):
        """Under braking (negative au), front axle loads should increase."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh_static = make_vehicle(weight=3400)
        veh_static = tire_forces(veh_static, 0, sim_defaults)
        front_static = veh_static.model.lf_fz[0] + veh_static.model.rf_fz[0]

        veh_brake = make_vehicle(weight=3400)
        veh_brake.model.au[0] = -25.76  # ~0.8g braking deceleration
        veh_brake = tire_forces(veh_brake, 0, sim_defaults)
        front_brake = veh_brake.model.lf_fz[0] + veh_brake.model.rf_fz[0]

        assert front_brake > front_static

    def test_braking_decreases_rear_load(self):
        """Under braking, rear axle loads should decrease."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh_static = make_vehicle(weight=3400)
        veh_static = tire_forces(veh_static, 0, sim_defaults)
        rear_static = veh_static.model.rr_fz[0] + veh_static.model.lr_fz[0]

        veh_brake = make_vehicle(weight=3400)
        veh_brake.model.au[0] = -25.76
        veh_brake = tire_forces(veh_brake, 0, sim_defaults)
        rear_brake = veh_brake.model.rr_fz[0] + veh_brake.model.lr_fz[0]

        assert rear_brake < rear_static

    def test_weight_transfer_conserves_total(self):
        """Even under braking, total Fz should still equal weight."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(weight=3400)
        veh.model.au[0] = -25.76
        veh = tire_forces(veh, 0, sim_defaults)

        total_fz = (veh.model.lf_fz[0] + veh.model.rf_fz[0] +
                    veh.model.rr_fz[0] + veh.model.lr_fz[0])
        assert total_fz == pytest.approx(3400, rel=1e-3)

    def test_lateral_weight_transfer(self):
        """Lateral acceleration should cause left-right weight shift."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(weight=3400)
        veh.model.av[0] = 16.1  # ~0.5g lateral accel
        veh = tire_forces(veh, 0, sim_defaults)

        # Positive av -> weight shifts from left to right (or vice versa)
        # With positive av, the hcg term adds to left, subtracts from right
        lf = veh.model.lf_fz[0]
        rf = veh.model.rf_fz[0]
        assert lf != pytest.approx(rf, abs=10)


# ---------------------------------------------------------------------------
# Throttle (FWD vs RWD)
# ---------------------------------------------------------------------------

class TestThrottle:

    def test_fwd_throttle_front_tires_only(self):
        """FWD throttle: front tires get drive force, rear tires do not."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(fwd=1, rwd=0, awd=0, vx=44.0)
        veh.driver_input.throttle[0] = 0.5
        veh = tire_forces(veh, 0, sim_defaults)

        # Front tires should have positive fx (drive force)
        assert veh.model.lf_fx[0] > 0
        assert veh.model.rf_fx[0] > 0
        # Rear tires should have ~0 fx (no throttle, no brake)
        assert veh.model.rr_fx[0] == pytest.approx(0, abs=1.0)
        assert veh.model.lr_fx[0] == pytest.approx(0, abs=1.0)

    def test_rwd_throttle_rear_tires_only(self):
        """RWD throttle: rear tires get drive force, front tires do not."""
        sim_defaults = {'mu_max': 0.8, 'alpha_max': 0.174533}
        veh = make_vehicle(fwd=0, rwd=1, awd=0, vx=44.0)
        veh.driver_input.throttle[0] = 0.5
        veh = tire_forces(veh, 0, sim_defaults)

        # Front tires should have ~0 fx
        assert veh.model.lf_fx[0] == pytest.approx(0, abs=1.0)
        assert veh.model.rf_fx[0] == pytest.approx(0, abs=1.0)
        # Rear tires should have positive fx
        assert veh.model.rr_fx[0] > 0
        assert veh.model.lr_fx[0] > 0
