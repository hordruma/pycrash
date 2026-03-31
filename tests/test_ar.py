"""
Tests for pycrash/functions/ar.py -- accident reconstruction equations.

All functions in ar.py are pure math operating in imperial units
(lb, in, mph, ft/s, ft-lb). We test against hand-calculated / known values.
"""
import pytest
import numpy as np

# Compatibility: np.trapz was removed in numpy 2.0
if not hasattr(np, 'trapz'):
    np.trapz = np.trapezoid

from pycrash.functions.ar import (
    ABfrombob1,
    CrushEnergyAB,
    CrushForceAB,
    StrikingDV,
    StruckDV,
    EnergyDV,
    formFactorin,
    BarrierCrushEnergy,
    cipriani_rest,
    CrushEnergyInt,
    SpringSeriesKeff,
    BEVfromE,
)


# ---------------------------------------------------------------------------
# A and B stiffness from bo / b1
# ---------------------------------------------------------------------------

class TestABfrombob1:
    """ABfrombob1(W, bo, b1, L) -> [A, B]"""

    def test_basic_calculation(self):
        W, bo, b1, L = 3000, 5, 3, 60
        A, B = ABfrombob1(W, bo, b1, L)
        # A = 0.802 * W * bo * b1 / L
        assert A == pytest.approx(0.802 * 3000 * 5 * 3 / 60, rel=1e-6)
        # B = 0.802 * W * b1^2 / L
        assert B == pytest.approx(0.802 * 3000 * 9 / 60, rel=1e-6)

    def test_A_proportional_to_weight(self):
        _, _ = ABfrombob1(2000, 5, 3, 60)
        A1, B1 = ABfrombob1(2000, 5, 3, 60)
        A2, B2 = ABfrombob1(4000, 5, 3, 60)
        assert A2 == pytest.approx(2 * A1, rel=1e-6)
        assert B2 == pytest.approx(2 * B1, rel=1e-6)

    def test_returns_list(self):
        result = ABfrombob1(3000, 5, 3, 60)
        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Crush Energy from A and B
# ---------------------------------------------------------------------------

class TestCrushEnergyAB:
    """CrushEnergyAB(A, B, L, C) -> energy in in-lb"""

    def test_zero_crush(self):
        # C = 0 -> energy should equal L * A^2 / (2*B)  (the "no-damage" threshold)
        A, B, L = 300, 150, 60
        energy = CrushEnergyAB(A, B, L, 0)
        expected = L * (A**2 / (2 * B))
        assert energy == pytest.approx(expected, rel=1e-6)

    def test_positive_crush(self):
        A, B, L, C = 300, 150, 60, 10
        energy = CrushEnergyAB(A, B, L, C)
        expected = L * (A * C + B * C**2 / 2 + A**2 / (2 * B))
        assert energy == pytest.approx(expected, rel=1e-6)

    def test_energy_increases_with_crush(self):
        A, B, L = 300, 150, 60
        e1 = CrushEnergyAB(A, B, L, 5)
        e2 = CrushEnergyAB(A, B, L, 10)
        assert e2 > e1

    def test_energy_proportional_to_L(self):
        A, B, C = 300, 150, 10
        e1 = CrushEnergyAB(A, B, 30, C)
        e2 = CrushEnergyAB(A, B, 60, C)
        assert e2 == pytest.approx(2 * e1, rel=1e-6)


# ---------------------------------------------------------------------------
# Crush Force from A and B
# ---------------------------------------------------------------------------

class TestCrushForceAB:
    """CrushForceAB(A, B, L, C) -> force in lb"""

    def test_zero_crush_gives_threshold_force(self):
        force = CrushForceAB(300, 150, 60, 0)
        assert force == pytest.approx(60 * 300, rel=1e-6)

    def test_linear_in_crush(self):
        A, B, L = 300, 150, 60
        f1 = CrushForceAB(A, B, L, 5)
        f2 = CrushForceAB(A, B, L, 10)
        # Force = L*(A + B*C), so delta-force is L*B*delta-C
        assert (f2 - f1) == pytest.approx(L * B * 5, rel=1e-6)


# ---------------------------------------------------------------------------
# Delta-V calculations
# ---------------------------------------------------------------------------

class TestDeltaV:
    """StrikingDV and StruckDV -- momentum-based delta-V in mph."""

    def test_equal_weight_equal_speed_full_rest(self):
        """Two equal cars at same closing speed with COR=1 (elastic):
        each should get delta-V equal to closing speed."""
        dv1 = StrikingDV(3000, 3000, 30, 0, 1.0)
        dv2 = StruckDV(3000, 3000, 30, 0, 1.0)
        assert dv1 == pytest.approx(30, rel=1e-3)
        assert dv2 == pytest.approx(30, rel=1e-3)

    def test_equal_weight_zero_rest(self):
        """Two equal cars, COR=0 (perfectly plastic): each gets half closing speed."""
        dv1 = StrikingDV(3000, 3000, 30, 0, 0)
        dv2 = StruckDV(3000, 3000, 30, 0, 0)
        assert dv1 == pytest.approx(15, rel=1e-3)
        assert dv2 == pytest.approx(15, rel=1e-3)

    def test_momentum_conservation(self):
        """m1*dv1 should equal m2*dv2 (magnitudes in fps)."""
        w1, w2, v1, v2, cor = 3400, 2900, 40, 0, 0.15
        dv1 = StrikingDV(w1, w2, v1, v2, cor)
        dv2 = StruckDV(w1, w2, v1, v2, cor)
        # Convert back to fps for momentum check
        m1, m2 = w1 / 32.2, w2 / 32.2
        assert m1 * dv1 == pytest.approx(m2 * dv2, rel=1e-3)

    def test_heavier_vehicle_smaller_dv(self):
        """Heavier striking vehicle should have smaller delta-V."""
        dv_heavy = StrikingDV(5000, 3000, 30, 0, 0.1)
        dv_light = StrikingDV(3000, 5000, 30, 0, 0.1)
        assert dv_heavy < dv_light

    def test_stationary_struck_vehicle(self):
        """Struck vehicle initially at rest should gain positive delta-V."""
        dv2 = StruckDV(3000, 3000, 30, 0, 0)
        assert dv2 > 0


# ---------------------------------------------------------------------------
# EnergyDV -- delta-V from dissipated energy
# ---------------------------------------------------------------------------

class TestEnergyDV:

    def test_returns_list_of_two(self):
        result = EnergyDV(3000, 3000, 50000, 0.1)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_equal_weights_equal_dv(self):
        """Equal weight vehicles should have equal delta-V."""
        result = EnergyDV(3000, 3000, 50000, 0.1)
        assert result[0] == pytest.approx(result[1], rel=1e-6)

    def test_heavier_vehicle_smaller_dv(self):
        result = EnergyDV(5000, 3000, 50000, 0.1)
        assert result[0] < result[1]  # heavier vehicle gets smaller dv

    def test_zero_energy_zero_dv(self):
        """No energy dissipated means no delta-V (COR must not be 1 to avoid div/0)."""
        result = EnergyDV(3000, 3000, 0, 0.5)
        assert result[0] == pytest.approx(0, abs=1e-6)
        assert result[1] == pytest.approx(0, abs=1e-6)


# ---------------------------------------------------------------------------
# Form factor
# ---------------------------------------------------------------------------

class TestFormFactor:

    def test_uniform_crush(self):
        """Uniform crush (all equal) should give form factor of 1.0."""
        crush = [10, 10, 10, 10, 10, 10]
        ff = formFactorin(crush)
        assert ff == pytest.approx(1.0, rel=1e-3)

    def test_non_uniform_crush(self):
        """Non-uniform crush should give form factor != 1."""
        crush = [0, 5, 10, 15, 10, 5]
        ff = formFactorin(crush)
        assert ff != pytest.approx(1.0, abs=0.01)
        assert ff > 0

    def test_zero_crush_produces_nan_or_inf(self):
        """All zero crush leads to division by zero in the formula, producing nan/inf."""
        crush = [0, 0, 0, 0, 0, 0]
        result = formFactorin(crush)
        assert np.isnan(result) or np.isinf(result)


# ---------------------------------------------------------------------------
# Barrier Crush Energy
# ---------------------------------------------------------------------------

class TestBarrierCrushEnergy:

    def test_basic_value(self):
        """KE = 0.5 * m * v^2 where m=W/32.2, v in fps."""
        W, s = 3000, 35  # lb, mph
        v_fps = s * 1.46667
        expected = 0.5 * (W / 32.2) * v_fps**2
        assert BarrierCrushEnergy(W, s) == pytest.approx(expected, rel=1e-4)

    def test_zero_speed(self):
        assert BarrierCrushEnergy(3000, 0) == pytest.approx(0, abs=1e-6)

    def test_proportional_to_weight(self):
        e1 = BarrierCrushEnergy(2000, 30)
        e2 = BarrierCrushEnergy(4000, 30)
        assert e2 == pytest.approx(2 * e1, rel=1e-6)

    def test_proportional_to_speed_squared(self):
        e1 = BarrierCrushEnergy(3000, 20)
        e2 = BarrierCrushEnergy(3000, 40)
        assert e2 == pytest.approx(4 * e1, rel=1e-4)


# ---------------------------------------------------------------------------
# Cipriani restitution
# ---------------------------------------------------------------------------

class TestCiprianiRest:

    def test_low_speed_high_restitution(self):
        """Low closing speed should yield higher restitution."""
        r_low = cipriani_rest(5)
        r_high = cipriani_rest(30)
        assert r_low > r_high

    def test_returns_positive_for_typical_speeds(self):
        """Restitution should be positive for speeds up to ~35 mph."""
        for s in [5, 10, 15, 20, 30]:
            r = cipriani_rest(s)
            assert r > 0

    def test_moderate_value(self):
        """At moderate speed (~15 mph), restitution should be between 0 and 1."""
        r = cipriani_rest(15)
        assert 0 < r < 1


# ---------------------------------------------------------------------------
# CrushEnergyInt -- numerical integration
# ---------------------------------------------------------------------------

class TestCrushEnergyInt:

    def test_rectangular(self):
        """Constant force over displacement should yield F * d."""
        dx = np.array([0, 0.5, 1.0])
        f = np.array([1000, 1000, 1000])
        energy = CrushEnergyInt(dx, f)
        assert energy == pytest.approx(1000, rel=1e-3)

    def test_triangular(self):
        """Triangular force-displacement: 0.5 * F_max * d."""
        dx = np.array([0, 0.5, 1.0])
        f = np.array([0, 500, 1000])
        energy = CrushEnergyInt(dx, f)
        assert energy == pytest.approx(500, rel=1e-3)


# ---------------------------------------------------------------------------
# Spring Series Keff
# ---------------------------------------------------------------------------

class TestSpringSeriesKeff:

    def test_equal_springs(self):
        """Two equal springs in series: Keff = k/2."""
        assert SpringSeriesKeff(100, 100) == pytest.approx(50, rel=1e-6)

    def test_known_values(self):
        """k1=60000, k2=40000 -> 1/(1/60000+1/40000) = 24000."""
        assert SpringSeriesKeff(60000, 40000) == pytest.approx(24000, rel=1e-6)

    def test_one_very_stiff(self):
        """If one spring is very stiff, effective ~ softer spring."""
        keff = SpringSeriesKeff(1e12, 1000)
        assert keff == pytest.approx(1000, rel=1e-3)


# ---------------------------------------------------------------------------
# BEV from Energy
# ---------------------------------------------------------------------------

class TestBEVfromE:

    def test_known_value(self):
        """BEV = sqrt(2*E / m) * 0.681818 (fps -> mph)"""
        W = 3000
        E = 100000  # ft-lb
        m = W / 32.2
        v_fps = np.sqrt(2 * E / m)
        expected_mph = v_fps * 0.681818
        assert BEVfromE(W, E) == pytest.approx(expected_mph, rel=1e-3)

    def test_zero_energy(self):
        assert BEVfromE(3000, 0) == pytest.approx(0, abs=1e-6)

    def test_round_trip_with_barrier_crush_energy(self):
        """BarrierCrushEnergy(W, s) -> E, then BEVfromE(W, E) should give back ~s."""
        W, s = 3000, 35
        E = BarrierCrushEnergy(W, s)
        bev = BEVfromE(W, E)
        assert bev == pytest.approx(s, rel=1e-2)
