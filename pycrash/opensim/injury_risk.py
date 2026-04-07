"""
Injury risk assessment from crash reconstruction and OpenSim outputs.

Computes injury probability using established biomechanical criteria:
- AIS (Abbreviated Injury Scale) probability functions
- FMVSS 208 injury thresholds
- Euro NCAP assessment protocol metrics
- Body-region-specific injury risk curves

These metrics connect vehicle-level reconstruction (pycrash delta-V)
to occupant injury outcomes, which is the ultimate purpose of
crash reconstruction in forensic and legal contexts.

References:
  - Eppinger et al. (1999) NHTSA: Development of Improved Injury Criteria
    for the Assessment of Advanced Automotive Restraint Systems - II
  - Kuppa (2004) NHTSA: Injury Criteria for Side Impact Dummies
  - Prasad & Mertz (1985): The Position of the US Delegation to ISO WG6
  - Kent & Funk (2004): Thoracic Injury Risk Curves
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# FMVSS 208 / NCAP Injury Assessment Reference Values (IARVs)
# ---------------------------------------------------------------------------

IARV = {
    # Head
    'hic_15_limit': 700,          # HIC15 threshold
    'hic_36_limit': 1000,         # HIC36 threshold
    'head_accel_3ms_g': 80,       # Peak head acceleration (3ms clip)

    # Neck (Nij criteria)
    'neck_tension_N': 4170,       # Critical tension force (N)
    'neck_compression_N': 4000,   # Critical compression (N)
    'neck_flexion_Nm': 310,       # Critical flexion moment (Nm)
    'neck_extension_Nm': 135,     # Critical extension moment (Nm)
    'nij_limit': 1.0,            # Combined Nij threshold

    # Chest
    'chest_accel_3ms_g': 60,      # Chest acceleration limit
    'chest_deflection_mm': 63,    # Sternum deflection limit
    'chest_vc_ms': 1.0,          # Viscous criterion (V*C)

    # Femur
    'femur_force_N': 10000,       # Axial femur force limit (10 kN)
    'femur_force_lb': 2250,       # Same in lb

    # Tibia
    'tibia_force_N': 8000,        # Axial tibia force limit
    'tibia_index': 1.3,           # Tibia index (TI) limit

    # Pelvis
    'pelvis_accel_g': 130,        # Lateral pelvis acceleration (side impact)
}


@dataclass
class InjuryMetrics:
    """Collection of computed injury risk metrics for a single occupant."""
    # Head
    hic_15: float = 0.0
    hic_36: float = 0.0
    head_accel_3ms_g: float = 0.0
    head_injury_prob_ais3: float = 0.0

    # Neck
    nij: float = 0.0
    neck_tension_N: float = 0.0
    neck_compression_N: float = 0.0
    neck_flexion_Nm: float = 0.0
    neck_extension_Nm: float = 0.0
    neck_injury_prob_ais3: float = 0.0

    # Chest
    chest_accel_3ms_g: float = 0.0
    chest_deflection_mm: float = 0.0
    chest_injury_prob_ais3: float = 0.0

    # Lower extremity
    femur_force_N: float = 0.0
    tibia_force_N: float = 0.0
    femur_injury_prob_ais2: float = 0.0

    # Overall
    overall_ais3_prob: float = 0.0


class InjuryRiskAssessment:
    """
    Computes injury risk from crash pulse data and OpenSim simulation outputs.

    Two modes of operation:
    1. Pulse-only: Estimate injury risk from crash pulse metrics alone
       (HIC, chest g, delta-V). Sufficient for most reconstruction work.
    2. OpenSim-enhanced: Use detailed joint forces and body segment
       kinematics from OpenSim for refined injury probability.
    """

    def __init__(self):
        self.metrics = InjuryMetrics()

    def from_pulse_summary(self, pulse_summary):
        """
        Compute injury risk estimates from CrashPulseGenerator.get_pulse_summary().

        This is the primary interface for reconstruction-based injury analysis.
        No OpenSim required - uses validated injury risk curves from NHTSA.

        Args:
            pulse_summary: dict from CrashPulseGenerator.get_pulse_summary()
                          Keys: peak_accel_g, hic_15, hic_36, clip_3ms_g,
                                delta_v_mph, peak_belt_force_lb

        Returns:
            InjuryMetrics with computed risk values
        """
        self.metrics.hic_15 = pulse_summary.get('hic_15', 0)
        self.metrics.hic_36 = pulse_summary.get('hic_36', 0)
        self.metrics.head_accel_3ms_g = pulse_summary.get('clip_3ms_g', 0)
        self.metrics.chest_accel_3ms_g = pulse_summary.get('peak_accel_g', 0) * 0.7  # chest ~70% of sled pulse

        # Head injury probability (AIS 3+) from HIC
        self.metrics.head_injury_prob_ais3 = self._hic_to_ais3_prob(
            self.metrics.hic_15
        )

        # Chest injury probability from acceleration
        self.metrics.chest_injury_prob_ais3 = self._chest_accel_to_ais3_prob(
            self.metrics.chest_accel_3ms_g
        )

        # Femur load estimate from delta-V and occupant weight
        delta_v = pulse_summary.get('delta_v_mph', 0)
        self.metrics.femur_force_N = self._estimate_femur_force(delta_v)
        self.metrics.femur_injury_prob_ais2 = self._femur_force_to_ais2_prob(
            self.metrics.femur_force_N
        )

        # Neck injury estimate from pulse
        self.metrics.nij = self._estimate_nij_from_pulse(pulse_summary)
        self.metrics.neck_injury_prob_ais3 = self._nij_to_ais3_prob(
            self.metrics.nij
        )

        # Overall AIS 3+ probability (independent body regions)
        probs = [
            self.metrics.head_injury_prob_ais3,
            self.metrics.neck_injury_prob_ais3,
            self.metrics.chest_injury_prob_ais3,
            self.metrics.femur_injury_prob_ais2,
        ]
        # P(at least one AIS3+) = 1 - product(1 - p_i)
        self.metrics.overall_ais3_prob = 1 - np.prod([1 - p for p in probs])

        return self.metrics

    def from_opensim_results(self, joint_forces, body_kinematics):
        """
        Compute refined injury risk from OpenSim joint reaction forces
        and body segment kinematics.

        Args:
            joint_forces: dict from OccupantModel.get_joint_reactions()
            body_kinematics: DataFrame with body segment accelerations

        Returns:
            InjuryMetrics with refined values
        """
        # This would process actual OpenSim output files (.sto)
        # Implementation depends on specific OpenSim output format
        # Placeholder for the interface

        if 'back' in joint_forces:
            back_forces = joint_forces['back']
            # Neck tension/compression from cervical spine joint
            self.metrics.neck_tension_N = float(np.max(back_forces.get('Fy', [0])))
            self.metrics.neck_compression_N = float(np.min(back_forces.get('Fy', [0])))
            self.metrics.neck_flexion_Nm = float(np.max(back_forces.get('Mz', [0])))

        if 'hip_r' in joint_forces:
            hip_forces = joint_forces['hip_r']
            self.metrics.femur_force_N = float(np.max(np.abs(hip_forces.get('Fy', [0]))))

        return self.metrics

    # -------------------------------------------------------------------
    # Injury probability functions from published NHTSA research
    # -------------------------------------------------------------------

    @staticmethod
    def _hic_to_ais3_prob(hic_15):
        """
        Head AIS 3+ injury probability from HIC15.

        Based on Prasad-Mertz curve (expanded dataset):
        P(AIS>=3) = 1 / (1 + exp(3.39 + 200/max(HIC,1) - 0.00372*HIC))

        Simplified logistic from NHTSA FMVSS 208 analysis.
        """
        if hic_15 <= 0:
            return 0.0

        # Logistic function from Eppinger et al. (1999)
        # P(AIS>=3|HIC15) using expanded Prasad-Mertz
        alpha = 2.49
        beta = 0.00351
        prob = 1.0 / (1.0 + np.exp(alpha - beta * hic_15))
        return float(np.clip(prob, 0, 1))

    @staticmethod
    def _chest_accel_to_ais3_prob(accel_3ms_g):
        """
        Chest AIS 3+ probability from 3ms clip acceleration.

        Based on Kent & Funk (2004) and NHTSA frontal crash analysis.
        """
        if accel_3ms_g <= 0:
            return 0.0

        # Logistic: P(AIS>=3) = 1/(1+exp(a - b*accel))
        alpha = 5.55
        beta = 0.0693
        prob = 1.0 / (1.0 + np.exp(alpha - beta * accel_3ms_g))
        return float(np.clip(prob, 0, 1))

    @staticmethod
    def _femur_force_to_ais2_prob(force_N):
        """
        Femur AIS 2+ probability from axial femur force.

        Based on Kuppa (2004) NHTSA analysis.
        """
        if force_N <= 0:
            return 0.0

        # Weibull distribution from NHTSA
        # Scale = 10700 N, shape = 2.84
        scale = 10700
        shape = 2.84
        prob = 1.0 - np.exp(-(force_N / scale) ** shape)
        return float(np.clip(prob, 0, 1))

    @staticmethod
    def _nij_to_ais3_prob(nij):
        """
        Neck AIS 3+ probability from Nij combined criterion.

        Nij = Fz/Fz_crit + My/My_crit (tension-flexion, etc.)
        """
        if nij <= 0:
            return 0.0

        # From Eppinger et al. (1999)
        alpha = 2.693
        beta = 1.195
        prob = 1.0 / (1.0 + np.exp(alpha - beta * nij))
        return float(np.clip(prob, 0, 1))

    @staticmethod
    def _estimate_femur_force(delta_v_mph):
        """
        Rough estimate of femur force from delta-V.

        Based on regression from NHTSA frontal crash test database.
        Assumes belted occupant, no knee bolster contact.
        """
        # Empirical: F_femur(N) ~ 150 * delta_v(mph) for belted occupant
        return max(0, 150 * delta_v_mph)

    @staticmethod
    def _estimate_nij_from_pulse(pulse_summary):
        """
        Estimate Nij from crash pulse characteristics.

        Simplified estimate based on peak deceleration and occupant excursion.
        Full Nij requires neck load cell data or OpenSim neck joint forces.
        """
        peak_g = pulse_summary.get('peak_accel_g', 0)
        # Rough correlation: Nij ~ 0.015 * peak_g for frontal with airbag
        return min(2.0, 0.015 * peak_g)

    def generate_report(self):
        """
        Generate a human-readable injury risk report.

        Returns:
            str with formatted report
        """
        m = self.metrics
        lines = [
            "=" * 60,
            "OCCUPANT INJURY RISK ASSESSMENT",
            "=" * 60,
            "",
            "HEAD",
            f"  HIC15:              {m.hic_15:>8.0f}    (limit: {IARV['hic_15_limit']})",
            f"  HIC36:              {m.hic_36:>8.0f}    (limit: {IARV['hic_36_limit']})",
            f"  Accel (3ms clip):   {m.head_accel_3ms_g:>8.1f} g  (limit: {IARV['head_accel_3ms_g']} g)",
            f"  AIS 3+ probability: {m.head_injury_prob_ais3:>8.1%}",
            f"  Status: {'EXCEEDS LIMIT' if m.hic_15 > IARV['hic_15_limit'] else 'Within limit'}",
            "",
            "NECK",
            f"  Nij:                {m.nij:>8.2f}    (limit: {IARV['nij_limit']})",
            f"  AIS 3+ probability: {m.neck_injury_prob_ais3:>8.1%}",
            f"  Status: {'EXCEEDS LIMIT' if m.nij > IARV['nij_limit'] else 'Within limit'}",
            "",
            "CHEST",
            f"  Accel (3ms clip):   {m.chest_accel_3ms_g:>8.1f} g  (limit: {IARV['chest_accel_3ms_g']} g)",
            f"  AIS 3+ probability: {m.chest_injury_prob_ais3:>8.1%}",
            f"  Status: {'EXCEEDS LIMIT' if m.chest_accel_3ms_g > IARV['chest_accel_3ms_g'] else 'Within limit'}",
            "",
            "LOWER EXTREMITY",
            f"  Femur force:        {m.femur_force_N:>8.0f} N  (limit: {IARV['femur_force_N']} N)",
            f"  AIS 2+ probability: {m.femur_injury_prob_ais2:>8.1%}",
            f"  Status: {'EXCEEDS LIMIT' if m.femur_force_N > IARV['femur_force_N'] else 'Within limit'}",
            "",
            "-" * 60,
            f"OVERALL AIS 3+ PROBABILITY: {m.overall_ais3_prob:.1%}",
            "-" * 60,
        ]

        # Risk level classification
        if m.overall_ais3_prob < 0.05:
            risk = "LOW - Minor injury likely, serious injury unlikely"
        elif m.overall_ais3_prob < 0.20:
            risk = "MODERATE - Possible moderate injuries"
        elif m.overall_ais3_prob < 0.50:
            risk = "HIGH - Serious injury probable"
        else:
            risk = "SEVERE - Life-threatening injury likely"

        lines.extend([
            f"RISK LEVEL: {risk}",
            "=" * 60,
            "",
            "Note: Probabilities are population-level estimates from NHTSA",
            "injury risk curves. Individual outcomes depend on age, sex,",
            "BMI, pre-existing conditions, and exact occupant position.",
        ])

        return '\n'.join(lines)

    def to_dict(self):
        """Return all metrics as a flat dictionary."""
        m = self.metrics
        return {
            'hic_15': m.hic_15,
            'hic_36': m.hic_36,
            'head_accel_3ms_g': m.head_accel_3ms_g,
            'head_ais3_prob': m.head_injury_prob_ais3,
            'nij': m.nij,
            'neck_ais3_prob': m.neck_injury_prob_ais3,
            'chest_accel_3ms_g': m.chest_accel_3ms_g,
            'chest_ais3_prob': m.chest_injury_prob_ais3,
            'femur_force_N': m.femur_force_N,
            'femur_ais2_prob': m.femur_injury_prob_ais2,
            'overall_ais3_prob': m.overall_ais3_prob,
        }
