"""
Tests for SDOF (Single Degree of Freedom) solver and spring models.

Modules under test:
  - pycrash/sdof_calcs/spring_models.py  (SpringForce, SpringFdx)
  - pycrash/sdof_calcs/sdof_calculations.py  (SingleDOFmodel, BrakeCheck, sign)
  - pycrash/sdof_model.py  (SDOF_Model class)
"""
import pytest
import numpy as np
import pandas as pd

from pycrash.sdof_calcs.spring_models import SpringForce, SpringFdx
from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel, BrakeCheck, sign


# ============================================================================
# sign() helper
# ============================================================================

class TestSign:

    def test_positive(self):
        assert sign(10) == 1

    def test_negative(self):
        assert sign(-5) == -1

    def test_zero(self):
        assert sign(0) == 0


# ============================================================================
# SpringForce -- constant stiffness model
# ============================================================================

class TestSpringForce:
    """
    SpringForce(dx, closing, k, input_k_disp, input_k_force, kreturn, dxperm)
    - input_k_disp, input_k_force are unused (set to 0)
    """

    def test_no_crush_returns_zero(self):
        """dx >= 0 means no contact -> force = 0."""
        assert SpringForce(0, 1, 50000, 0, 0, np.nan, np.nan) == 0
        assert SpringForce(0.1, 1, 50000, 0, 0, np.nan, np.nan) == 0

    def test_closing_force_proportional_to_crush(self):
        """During closing, force = k * |dx|."""
        k = 50000
        dx = -0.5  # 0.5 ft of crush
        force = SpringForce(dx, 1, k, 0, 0, np.nan, np.nan)
        assert force == pytest.approx(k * 0.5, rel=1e-6)

    def test_closing_force_scales_with_stiffness(self):
        dx = -0.25
        f1 = SpringForce(dx, 1, 50000, 0, 0, np.nan, np.nan)
        f2 = SpringForce(dx, 1, 100000, 0, 0, np.nan, np.nan)
        assert f2 == pytest.approx(2 * f1, rel=1e-6)

    def test_separating_force_uses_kreturn(self):
        """During separation (closing=0), force = kreturn * |dx - dxperm|."""
        dxperm = -0.3
        kreturn = 80000
        dx = -0.4  # still compressed past dxperm
        force = SpringForce(dx, 0, 50000, 0, 0, kreturn, dxperm)
        assert force == pytest.approx(kreturn * abs(dx - dxperm), rel=1e-6)

    def test_separating_past_dxperm_returns_zero(self):
        """Once dx >= dxperm during separation, force = 0."""
        dxperm = -0.3
        kreturn = 80000
        dx = -0.2  # less crush than permanent -> vehicles separated
        force = SpringForce(dx, 0, 50000, 0, 0, kreturn, dxperm)
        assert force == 0

    def test_separating_at_dxperm_returns_zero(self):
        dxperm = -0.3
        kreturn = 80000
        force = SpringForce(-0.3, 0, 50000, 0, 0, kreturn, dxperm)
        assert force == 0


# ============================================================================
# SpringFdx -- table-based stiffness model
# ============================================================================

class TestSpringFdx:

    @pytest.fixture
    def table_data(self):
        """Simple force-displacement table: displacement [ft], force [lb]."""
        disp = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        force = np.array([0, 5000, 15000, 30000, 50000])
        return disp, force

    def test_no_crush_returns_zero(self, table_data):
        disp, force = table_data
        assert SpringFdx(0, 1, 0, disp, force, np.nan, np.nan) == 0
        assert SpringFdx(0.1, 1, 0, disp, force, np.nan, np.nan) == 0

    def test_closing_interpolates_table(self, table_data):
        disp, force = table_data
        dx = -0.25  # should map to 5000 lb
        f = SpringFdx(dx, 1, 0, disp, force, np.nan, np.nan)
        assert f == pytest.approx(5000, rel=1e-3)

    def test_closing_interpolates_midpoint(self, table_data):
        disp, force = table_data
        dx = -0.375  # between 0.25 and 0.5 -> interpolate between 5000 and 15000
        f = SpringFdx(dx, 1, 0, disp, force, np.nan, np.nan)
        expected = np.interp(0.375, disp, force)
        assert f == pytest.approx(expected, rel=1e-3)

    def test_separating_uses_kreturn(self, table_data):
        disp, force = table_data
        dxperm = -0.2
        kreturn = 60000
        dx = -0.4
        f = SpringFdx(dx, 0, 0, disp, force, kreturn, dxperm)
        assert f == pytest.approx(kreturn * abs(dx - dxperm), rel=1e-6)

    def test_separating_past_dxperm_zero(self, table_data):
        disp, force = table_data
        dxperm = -0.3
        kreturn = 60000
        f = SpringFdx(-0.2, 0, 0, disp, force, kreturn, dxperm)
        assert f == 0


# ============================================================================
# BrakeCheck
# ============================================================================

class TestBrakeCheck:

    def test_moving_forward_full_brake(self):
        """Brake opposes motion when vehicle moves forward."""
        bf = BrakeCheck(1000, 5000, 10)
        assert bf == -1000

    def test_no_brake_applied(self):
        assert BrakeCheck(0, 5000, 0) == 0

    def test_stopped_spring_exceeds_brake(self):
        """Vehicle stopped, spring force > brake: full brake applied."""
        bf = BrakeCheck(500, -1000, 0)
        assert bf == -500

    def test_stopped_brake_exceeds_spring(self):
        """Vehicle stopped, brake > spring: force = -springF (prevents motion)."""
        bf = BrakeCheck(5000, -1000, 0)
        assert bf == pytest.approx(1000, rel=1e-6)


# ============================================================================
# SingleDOFmodel -- full iterative solver
# ============================================================================

class TestSingleDOFmodel:

    def test_basic_run_returns_dataframe(self):
        """Model should return a DataFrame with expected columns."""
        result = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0,
            W2=3000, v2_initial=0, v2_brake=0,
            k=50000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        assert isinstance(result, pd.DataFrame)
        expected_cols = ['t', 'x1', 'x2', 'v1', 'v2', 'a1', 'a2',
                         'springF', 'dx', 'v1_brakeF', 'v2_brakeF']
        for col in expected_cols:
            assert col in result.columns

    def test_momentum_conservation_no_braking(self):
        """Total momentum should be conserved when no braking is applied."""
        W1, W2 = 3400, 2900
        m1, m2 = W1 / 32.2, W2 / 32.2
        v1_mph, v2_mph = 30, 0

        result = SingleDOFmodel(
            W1=W1, v1_initial=v1_mph, v1_brake=0,
            W2=W2, v2_initial=v2_mph, v2_brake=0,
            k=50000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )

        # Initial momentum (fps)
        p_initial = m1 * (v1_mph * 1.46667) + m2 * (v2_mph * 1.46667)

        # Final momentum
        p_final = m1 * result.v1.iloc[-1] + m2 * result.v2.iloc[-1]

        assert p_final == pytest.approx(p_initial, rel=1e-3)

    def test_momentum_conservation_with_different_weights(self):
        """Momentum conservation with unequal vehicles."""
        W1, W2 = 5000, 2500
        m1, m2 = W1 / 32.2, W2 / 32.2

        result = SingleDOFmodel(
            W1=W1, v1_initial=40, v1_brake=0,
            W2=W2, v2_initial=0, v2_brake=0,
            k=60000, cor=0.1, tstop=0.5,
            ktype='constantK', ttype=1
        )

        p_initial = m1 * (40 * 1.46667)
        p_final = m1 * result.v1.iloc[-1] + m2 * result.v2.iloc[-1]
        assert p_final == pytest.approx(p_initial, rel=1e-3)

    def test_common_velocity_reached(self):
        """Vehicles should reach a common velocity during impact (at min dx).
        Using small COR to avoid division by zero in kreturn calculation."""
        W1, W2 = 3000, 3000
        m1, m2 = W1 / 32.2, W2 / 32.2

        result = SingleDOFmodel(
            W1=W1, v1_initial=30, v1_brake=0,
            W2=W2, v2_initial=0, v2_brake=0,
            k=50000, cor=0.01, tstop=0.5,
            ktype='constantK', ttype=1
        )

        # At max crush (min dx), velocities should be approximately equal
        idx_maxcrush = result.dx.idxmin()
        v1_common = result.v1.iloc[idx_maxcrush]
        v2_common = result.v2.iloc[idx_maxcrush]
        assert v1_common == pytest.approx(v2_common, abs=0.5)

    def test_cor_near_zero_plastic_collision(self):
        """COR~0 (near-plastic): final velocities should be approximately equal.
        COR=0 exactly causes division by zero in the SDOF solver, so use 0.01."""
        W1, W2 = 3000, 3000

        result = SingleDOFmodel(
            W1=W1, v1_initial=30, v1_brake=0,
            W2=W2, v2_initial=0, v2_brake=0,
            k=50000, cor=0.01, tstop=0.5,
            ktype='constantK', ttype=1
        )

        # For nearly plastic collision, final v1 ~ final v2
        assert result.v1.iloc[-1] == pytest.approx(result.v2.iloc[-1], abs=1.0)

    def test_cor_one_elastic_collision(self):
        """COR=1: kinetic energy should be approximately conserved."""
        W1, W2 = 3000, 3000
        m1, m2 = W1 / 32.2, W2 / 32.2
        v1_fps = 30 * 1.46667

        result = SingleDOFmodel(
            W1=W1, v1_initial=30, v1_brake=0,
            W2=W2, v2_initial=0, v2_brake=0,
            k=50000, cor=1.0, tstop=1.0,
            ktype='constantK', ttype=1
        )

        ke_initial = 0.5 * m1 * v1_fps**2
        ke_final = 0.5 * m1 * result.v1.iloc[-1]**2 + 0.5 * m2 * result.v2.iloc[-1]**2
        assert ke_final == pytest.approx(ke_initial, rel=0.02)

    def test_vehicles_separating_at_onset_stops_immediately(self):
        """If v2 >= v1, vehicles are separating -> model stops."""
        result = SingleDOFmodel(
            W1=3000, v1_initial=20, v1_brake=0,
            W2=3000, v2_initial=30, v2_brake=0,
            k=50000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        # Should return an empty or minimal DataFrame
        assert len(result) <= 1

    def test_spring_force_returns_to_zero(self):
        """Spring force should return to zero after vehicles separate."""
        result = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0,
            W2=3000, v2_initial=0, v2_brake=0,
            k=50000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        # Last spring force should be 0 or very close
        assert result.springF.iloc[-1] == pytest.approx(0, abs=10)

    def test_braking_reduces_final_velocity(self):
        """Braking on v1 should reduce v1 final speed compared to no braking."""
        result_no_brake = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0,
            W2=3000, v2_initial=0, v2_brake=0,
            k=50000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        result_brake = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0.5,
            W2=3000, v2_initial=0, v2_brake=0,
            k=50000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        # With braking, v1 final should be lower
        assert result_brake.v1.iloc[-1] < result_no_brake.v1.iloc[-1]

    def test_peak_crush_positive_closing_speed(self):
        """Peak mutual crush should be negative (compression)."""
        result = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0,
            W2=3000, v2_initial=0, v2_brake=0,
            k=50000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        assert min(result.dx) < 0

    def test_higher_stiffness_less_crush(self):
        """Higher stiffness should produce less peak mutual crush."""
        result_soft = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0,
            W2=3000, v2_initial=0, v2_brake=0,
            k=30000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        result_stiff = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0,
            W2=3000, v2_initial=0, v2_brake=0,
            k=100000, cor=0.15, tstop=0.5,
            ktype='constantK', ttype=1
        )
        assert abs(min(result_stiff.dx)) < abs(min(result_soft.dx))

    def test_table_stiffness_runs(self):
        """Model should run with table-based stiffness (ktype='tableK')."""
        k_table = pd.DataFrame({
            'disp': [0, 0.25, 0.5, 0.75, 1.0],
            'force': [0, 5000, 15000, 30000, 50000]
        })

        result = SingleDOFmodel(
            W1=3000, v1_initial=30, v1_brake=0,
            W2=3000, v2_initial=0, v2_brake=0,
            k=k_table, cor=0.15, tstop=0.5,
            ktype='tableK', ttype=1
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 1


# ============================================================================
# SDOF_Model class (integration test)
# ============================================================================

class TestSDOFModelClass:

    def test_sdof_model_creation_and_run(self, camry_vehicle, civic_vehicle):
        """SDOF_Model should create, run simulation, and produce results."""
        from pycrash.sdof_model import SDOF_Model

        model_inputs = {
            'name': 'test_run',
            'cor': 0.15,
            'k': 50000,
            'tstop': 0.5,
        }

        sdof = SDOF_Model(camry_vehicle, civic_vehicle, model_inputs=model_inputs)
        assert hasattr(sdof, 'model')
        assert isinstance(sdof.model, pd.DataFrame)
        assert len(sdof.model) > 1

    def test_sdof_model_momentum_conservation(self, camry_vehicle, civic_vehicle):
        """Verify momentum conservation through the SDOF_Model class."""
        from pycrash.sdof_model import SDOF_Model

        model_inputs = {
            'name': 'momentum_test',
            'cor': 0.15,
            'k': 50000,
            'tstop': 0.5,
        }

        sdof = SDOF_Model(camry_vehicle, civic_vehicle, model_inputs=model_inputs)

        W1 = camry_vehicle.weight
        W2 = civic_vehicle.weight
        m1 = W1 / 32.2
        m2 = W2 / 32.2

        p_initial = m1 * sdof.model.v1.iloc[0] + m2 * sdof.model.v2.iloc[0]
        p_final = m1 * sdof.model.v1.iloc[-1] + m2 * sdof.model.v2.iloc[-1]

        assert p_final == pytest.approx(p_initial, rel=1e-3)

    def test_sdof_model_crush_energy(self, camry_vehicle, civic_vehicle):
        """crush_energy() should return a dictionary with energy values."""
        from pycrash.sdof_model import SDOF_Model

        model_inputs = {
            'name': 'energy_test',
            'cor': 0.15,
            'k': 50000,
            'tstop': 0.5,
        }

        sdof = SDOF_Model(camry_vehicle, civic_vehicle, model_inputs=model_inputs)
        energy = sdof.crush_energy()

        assert isinstance(energy, dict)
        assert 'mutual_energy_absorbed' in energy
        assert 'mutual_energy_returned' in energy
        assert energy['mutual_energy_absorbed'] < 0  # negative because dx is negative
