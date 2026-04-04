"""
Converts between pycrash Vehicle objects and BeamNG.tech vehicle configurations.

pycrash uses imperial units (ft, lb, mph, deg) while BeamNG uses metric (m, kg, m/s, rad).
This module handles all unit conversions and parameter mapping.
"""

import numpy as np

# Unit conversion constants
FT_TO_M = 0.3048
LB_TO_KG = 0.453592
MPH_TO_MS = 0.44704
IN_TO_M = 0.0254
DEG_TO_RAD = np.pi / 180.0
LBFTS2_TO_KGMS2 = 1.35582  # lb-ft-s^2 to kg-m^2

# BeamNG vehicle model mapping: real-world vehicle classes to BeamNG equivalents
# Users can extend this map or override with exact BeamNG model names
VEHICLE_CLASS_MAP = {
    "sedan": "etk800",
    "compact": "etki",
    "suv": "moonhawk",
    "pickup": "d15",
    "sports": "vivace",
    "van": "van",
    "coupe": "covet",
    "midsize": "etk800",
    "fullsize": "bluebuck",
    "default": "etk800",
}


class VehicleConverter:
    """
    Converts pycrash Vehicle objects to BeamNG vehicle configurations and back.

    The converter maps pycrash's 2D vehicle parameters (dimensions, mass, initial
    conditions) to BeamNG's 3D vehicle setup, handling unit conversions and
    coordinate system differences.

    pycrash coordinate system: X-forward, Y-left, angles CCW from X-axis (degrees)
    BeamNG coordinate system: X-east, Y-north, Z-up, angles CW from north (degrees)
    """

    def __init__(self, beamng_home=None):
        """
        Args:
            beamng_home: Path to BeamNG.tech installation directory.
                         If None, relies on BEAMNG_HOME environment variable.
        """
        self.beamng_home = beamng_home

    @staticmethod
    def pycrash_to_beamng_pos(x_ft, y_ft, origin_offset=(0, 0)):
        """
        Convert pycrash position (ft) to BeamNG world position (m).

        Args:
            x_ft: X position in feet (pycrash frame)
            y_ft: Y position in feet (pycrash frame)
            origin_offset: (x, y) offset in meters to place the scene in BeamNG world

        Returns:
            (bng_x, bng_y, bng_z): BeamNG world coordinates in meters.
                                    Z is set to 0 (ground level).
        """
        bng_x = x_ft * FT_TO_M + origin_offset[0]
        bng_y = y_ft * FT_TO_M + origin_offset[1]
        return (bng_x, bng_y, 0.0)

    @staticmethod
    def pycrash_to_beamng_heading(head_angle_deg):
        """
        Convert pycrash heading angle to BeamNG rotation.

        pycrash: degrees CCW from positive X-axis
        BeamNG: quaternion rotation (uses Euler internally: heading CW from north)

        Returns:
            (rx, ry, rz, rw): BeamNG quaternion rotation
        """
        # Convert to BeamNG heading: CW from north (Y-axis)
        bng_heading_deg = 90.0 - head_angle_deg
        bng_heading_rad = bng_heading_deg * DEG_TO_RAD
        # Convert to quaternion (rotation around Z-axis only for 2D heading)
        rw = np.cos(bng_heading_rad / 2)
        rz = np.sin(bng_heading_rad / 2)
        return (0.0, 0.0, rz, rw)

    @staticmethod
    def pycrash_to_beamng_velocity(vx_mph, vy_mph, head_angle_deg):
        """
        Convert pycrash vehicle-frame velocities to BeamNG world-frame velocities.

        Args:
            vx_mph: Forward velocity in mph (vehicle frame)
            vy_mph: Lateral velocity in mph (vehicle frame)
            head_angle_deg: Vehicle heading angle in degrees

        Returns:
            (vx_ms, vy_ms, vz_ms): World-frame velocity in m/s
        """
        vx_ms = vx_mph * MPH_TO_MS
        vy_ms = vy_mph * MPH_TO_MS
        theta = head_angle_deg * DEG_TO_RAD

        # Rotate from vehicle frame to world frame
        world_vx = vx_ms * np.cos(theta) - vy_ms * np.sin(theta)
        world_vy = vx_ms * np.sin(theta) + vy_ms * np.cos(theta)

        return (world_vx, world_vy, 0.0)

    def to_beamng_config(self, pycrash_vehicle, beamng_model=None, color="White",
                         origin_offset=(0, 0)):
        """
        Convert a pycrash Vehicle to a BeamNG vehicle configuration dict.

        Args:
            pycrash_vehicle: pycrash Vehicle instance
            beamng_model: BeamNG vehicle model name (e.g., 'etk800').
                          If None, attempts to map from vehicle class.
            color: Vehicle color string for BeamNG
            origin_offset: World coordinate offset (x_m, y_m) for scene placement

        Returns:
            dict with keys:
                'name': vehicle identifier
                'model': BeamNG model name
                'color': color string
                'pos': (x, y, z) in meters
                'rot': (rx, ry, rz, rw) quaternion
                'velocity': (vx, vy, vz) in m/s
                'pycrash_params': dict of converted physical parameters
        """
        veh = pycrash_vehicle

        # Determine BeamNG model
        if beamng_model is None:
            beamng_model = VEHICLE_CLASS_MAP.get("default", "etk800")

        # Convert position
        pos = self.pycrash_to_beamng_pos(
            getattr(veh, 'init_x_pos', 0),
            getattr(veh, 'init_y_pos', 0),
            origin_offset
        )

        # Convert heading
        rot = self.pycrash_to_beamng_heading(
            getattr(veh, 'head_angle', 0)
        )

        # Convert velocity
        velocity = self.pycrash_to_beamng_velocity(
            getattr(veh, 'vx_initial', 0),
            getattr(veh, 'vy_initial', 0),
            getattr(veh, 'head_angle', 0)
        )

        # Convert physical parameters for reference
        params = {
            'mass_kg': getattr(veh, 'weight', 0) * LB_TO_KG,
            'length_m': getattr(veh, 'length', 0) * FT_TO_M,
            'width_m': getattr(veh, 'width', 0) * FT_TO_M,
            'wheelbase_m': getattr(veh, 'wb', 0) * FT_TO_M,
            'cg_height_m': getattr(veh, 'hcg', 0) * FT_TO_M,
            'cg_to_front_m': getattr(veh, 'lcgf', 0) * FT_TO_M,
            'cg_to_rear_m': getattr(veh, 'lcgr', 0) * FT_TO_M,
            'track_width_m': getattr(veh, 'track', 0) * FT_TO_M,
            'izz_kgm2': getattr(veh, 'izz', 0) * LBFTS2_TO_KGMS2,
            'speed_ms': getattr(veh, 'vx_initial', 0) * MPH_TO_MS,
            'speed_mph': getattr(veh, 'vx_initial', 0),
            'stiffness_A': getattr(veh, 'A', 0),
            'stiffness_B': getattr(veh, 'B', 0),
        }

        return {
            'name': veh.name,
            'model': beamng_model,
            'color': color,
            'pos': pos,
            'rot': rot,
            'velocity': velocity,
            'pycrash_params': params,
        }

    @staticmethod
    def beamng_to_pycrash_dict(bng_state, vehicle_name="BeamNG_Vehicle"):
        """
        Convert BeamNG vehicle state data to a pycrash-compatible input dict.

        Useful for importing BeamNG simulation results back into pycrash
        for further analytical modeling.

        Args:
            bng_state: dict with BeamNG vehicle state keys:
                       'pos' (x,y,z in m), 'vel' (vx,vy,vz in m/s),
                       'rot' (quaternion), 'mass' (kg)
            vehicle_name: Name for the pycrash Vehicle

        Returns:
            dict compatible with pycrash Vehicle(name, input_dict=...)
        """
        pos = bng_state.get('pos', (0, 0, 0))
        vel = bng_state.get('vel', (0, 0, 0))
        mass_kg = bng_state.get('mass', 1500)

        # Extract heading from quaternion
        rot = bng_state.get('rot', (0, 0, 0, 1))
        # Heading from quaternion Z-rotation
        heading_rad = 2 * np.arctan2(rot[2], rot[3])
        heading_deg = 90.0 - (heading_rad / DEG_TO_RAD)  # BeamNG -> pycrash

        # World velocity to vehicle-frame velocity
        cos_h = np.cos(heading_deg * DEG_TO_RAD)
        sin_h = np.sin(heading_deg * DEG_TO_RAD)
        veh_vx = vel[0] * cos_h + vel[1] * sin_h
        veh_vy = -vel[0] * sin_h + vel[1] * cos_h

        return {
            'init_x_pos': pos[0] / FT_TO_M,
            'init_y_pos': pos[1] / FT_TO_M,
            'head_angle': heading_deg,
            'vx_initial': veh_vx / MPH_TO_MS,
            'vy_initial': veh_vy / MPH_TO_MS,
            'omega_z': 0,
            'weight': mass_kg / LB_TO_KG,
        }
