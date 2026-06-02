"""Claude tool definitions for crash reconstruction extraction."""
from __future__ import annotations

EXTRACT_VEHICLE_TOOL = {
    "name": "extract_vehicle",
    "description": "Extract vehicle information from a crash report. Call once per vehicle involved.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vehicle_number": {
                "type": "integer",
                "description": "Vehicle number (1, 2, etc.) as referenced in the report",
            },
            "year": {"type": "integer", "description": "Model year of the vehicle"},
            "make": {"type": "string", "description": "Vehicle manufacturer (e.g., Toyota, Ford)"},
            "model": {"type": "string", "description": "Vehicle model (e.g., Camry, F-150)"},
            "estimated_speed_mph": {
                "type": "number",
                "description": "Estimated travel speed in mph. Use witness estimates, speed limit, or skid mark analysis.",
            },
            "travel_direction": {
                "type": "string",
                "enum": ["northbound", "southbound", "eastbound", "westbound",
                         "northeast", "northwest", "southeast", "southwest"],
                "description": "Direction of travel at time of crash",
            },
            "role": {
                "type": "string",
                "enum": ["striking", "struck", "unknown"],
                "description": "Whether this vehicle struck the other or was struck",
            },
            "damage_location": {
                "type": "string",
                "enum": ["front", "rear", "left_side", "right_side",
                         "front_left", "front_right", "rear_left", "rear_right"],
                "description": "Primary area of damage on this vehicle",
            },
            "damage_description": {
                "type": "string",
                "description": "Description of damage extent and characteristics",
            },
            "driver_action": {
                "type": "string",
                "description": "What the driver was doing (braking, turning, accelerating, etc.)",
            },
            "confidence": {
                "type": "number",
                "minimum": 0, "maximum": 1,
                "description": "Confidence in the extracted data (0-1)",
            },
        },
        "required": ["vehicle_number", "role", "confidence"],
    },
}

EXTRACT_CRASH_CONDITIONS_TOOL = {
    "name": "extract_crash_conditions",
    "description": "Extract overall crash conditions and configuration.",
    "input_schema": {
        "type": "object",
        "properties": {
            "crash_type": {
                "type": "string",
                "enum": ["rear_end", "head_on", "intersection_angle",
                         "sideswipe_same", "sideswipe_opposite", "single_vehicle", "other"],
                "description": "Type/configuration of the crash",
            },
            "impact_angle_deg": {
                "type": "number",
                "description": "Angle between vehicle headings at impact (0=same direction, 180=head-on)",
            },
            "closing_speed_mph": {
                "type": "number",
                "description": "Estimated closing speed (relative speed at impact) in mph",
            },
            "suggested_model": {
                "type": "string",
                "enum": ["sdof", "impc", "sideswipe"],
                "description": "Recommended simulation model based on crash type. sdof for inline impacts, impc for angled impacts, sideswipe for glancing.",
            },
            "skid_marks_vehicle1_ft": {
                "type": "number",
                "description": "Pre-impact skid mark length for vehicle 1 in feet",
            },
            "skid_marks_vehicle2_ft": {
                "type": "number",
                "description": "Pre-impact skid mark length for vehicle 2 in feet",
            },
            "confidence": {
                "type": "number", "minimum": 0, "maximum": 1,
            },
        },
        "required": ["crash_type", "suggested_model", "confidence"],
    },
}

EXTRACT_SCENE_TOOL = {
    "name": "extract_scene",
    "description": "Extract scene and environmental conditions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "road_surface": {
                "type": "string",
                "enum": ["dry_asphalt", "wet_asphalt", "dry_concrete", "wet_concrete",
                         "gravel", "ice", "snow", "unknown"],
            },
            "suggested_friction": {
                "type": "number", "minimum": 0.1, "maximum": 1.0,
                "description": "Suggested tire-road friction coefficient based on surface condition",
            },
            "weather": {
                "type": "string",
                "enum": ["clear", "rain", "snow", "fog", "unknown"],
            },
            "speed_limit_mph": {"type": "number"},
            "road_grade_pct": {"type": "number", "description": "Road grade in percent (positive = uphill)"},
            "intersection_type": {
                "type": "string",
                "enum": ["none", "signalized", "stop_sign", "yield", "uncontrolled", "roundabout"],
            },
            "lighting": {
                "type": "string",
                "enum": ["daylight", "dawn_dusk", "dark_lighted", "dark_unlighted", "unknown"],
            },
        },
        "required": ["road_surface", "suggested_friction"],
    },
}

ALL_TOOLS = [
    EXTRACT_VEHICLE_TOOL,
    EXTRACT_CRASH_CONDITIONS_TOOL,
    EXTRACT_SCENE_TOOL,
]
