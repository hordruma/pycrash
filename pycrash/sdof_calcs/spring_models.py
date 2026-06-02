from __future__ import annotations
from typing import Optional, Union
import numpy as np


def SpringFdx(dx: float, closing: int, k: float, input_k_disp: np.ndarray,
              input_k_force: np.ndarray, kreturn: float, dxperm: float) -> float:
    """
    spring force using lookup table of displacement [ft], force [lb]
    input_k_disp from model - [ft]
    input_k_force from input - [lb]
    k - unused
    """
    if dx >= 0:
        return 0

    if closing == 1:
        return np.interp(-1*dx, input_k_disp, input_k_force)

    if (closing == 0) & ((dx - dxperm) < 0):  # separating and dx has not reached dxperm
        return kreturn * abs(dx - dxperm)

    if (closing == 0) & ((dx - dxperm) >= 0):  # separating and dx is less than dxperm
        return 0

def SpringForce(dx: float, closing: int, k: float, input_k_disp: float,
                input_k_force: float, kreturn: float, dxperm: float) -> float:
    """
    Spring force using linear spring assumption
    k - spring stiffness [lb/ft]
    input_k_disp - unused
    input_k_force - unused
    """
    if dx >= 0:
        return 0

    if closing == 1:
        return k * abs(dx)

    if (closing == 0) & ((dx - dxperm) < 0):  # closing and dx has not reached dxperm
        return kreturn * abs(dx - dxperm)

    if (closing == 0) & ((dx - dxperm) >= 0):  # closing and dx is less than dxperm
        return 0
