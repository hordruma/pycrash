"""Claude-powered crash report extraction agent."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pycrash_ai.api.config import settings
from pycrash_ai.api.agent.tools import ALL_TOOLS
from pycrash_ai.api.models import ExtractionResponse, ExtractedVehicle, ExtractedScene


SYSTEM_PROMPT = """You are a crash reconstruction specialist assistant. Your job is to extract structured data from police crash reports, witness statements, and crash descriptions.

You work in the field of forensic accident reconstruction. You understand:
- Vehicle dynamics, impact mechanics, and crash physics
- Police report terminology (V1, V2, POI, AoI, CDC codes)
- Common crash configurations (rear-end, intersection, sideswipe, head-on)
- Speed estimation from skid marks, witness statements, and damage

IMPORTANT RULES:
1. Only extract information that is explicitly stated or clearly implied in the text
2. If information is ambiguous, set confidence lower and note it
3. Never invent or assume speeds unless evidence supports it
4. Use the appropriate tool for each piece of information
5. Call extract_vehicle once for each vehicle mentioned
6. Call extract_crash_conditions once for the overall crash
7. Call extract_scene once for environmental conditions

For suggested_model selection:
- Use "sdof" for inline/collinear impacts (rear-end, head-on where vehicles stay in line)
- Use "impc" for angled impacts (intersection crashes, offset frontal)
- Use "sideswipe" for glancing/sliding contact"""


async def extract_from_text(text: str) -> ExtractionResponse:
    """Extract crash data from text using Claude."""
    if not settings.anthropic_api_key:
        return _mock_extraction(text)

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        messages=[
            {
                "role": "user",
                "content": f"Extract all crash data from the following report:\n\n{text}",
            }
        ],
    )

    # Process tool use responses
    vehicles: List[ExtractedVehicle] = []
    crash_type: Optional[str] = None
    scene: Optional[ExtractedScene] = None
    suggested_model: Optional[str] = None
    raw: Dict[str, Any] = {"tool_calls": []}

    for block in message.content:
        if block.type == "tool_use":
            raw["tool_calls"].append({"name": block.name, "input": block.input})

            if block.name == "extract_vehicle":
                vehicles.append(ExtractedVehicle(
                    year=block.input.get("year"),
                    make=block.input.get("make"),
                    model=block.input.get("model"),
                    estimated_speed_mph=block.input.get("estimated_speed_mph"),
                    travel_direction=block.input.get("travel_direction"),
                    role=block.input.get("role"),
                    damage_description=block.input.get("damage_description"),
                    confidence=block.input.get("confidence", 0.5),
                ))
            elif block.name == "extract_crash_conditions":
                crash_type = block.input.get("crash_type")
                suggested_model = block.input.get("suggested_model")
            elif block.name == "extract_scene":
                scene = ExtractedScene(
                    road_surface=block.input.get("road_surface"),
                    weather=block.input.get("weather"),
                    skid_marks_ft=block.input.get("skid_marks_vehicle1_ft"),
                    speed_limit_mph=block.input.get("speed_limit_mph"),
                    confidence=block.input.get("confidence", 0.5),
                )

    return ExtractionResponse(
        vehicles=vehicles,
        crash_type=crash_type,
        scene=scene,
        suggested_model=suggested_model,
        raw_extraction=raw,
    )


def _mock_extraction(text: str) -> ExtractionResponse:
    """Mock extraction when no API key is set. Useful for testing."""
    text_lower = text.lower()

    # Simple heuristic extraction for demo/testing
    vehicles = []
    if any(w in text_lower for w in ["vehicle 1", "v1", "striking"]):
        vehicles.append(ExtractedVehicle(
            role="striking",
            estimated_speed_mph=35,
            confidence=0.3,
        ))
    if any(w in text_lower for w in ["vehicle 2", "v2", "struck"]):
        vehicles.append(ExtractedVehicle(
            role="struck",
            estimated_speed_mph=0,
            confidence=0.3,
        ))

    # Default to two vehicles if none found
    if not vehicles:
        vehicles = [
            ExtractedVehicle(role="striking", confidence=0.1),
            ExtractedVehicle(role="struck", confidence=0.1),
        ]

    crash_type = "rear_end"
    if "intersection" in text_lower:
        crash_type = "intersection_angle"
    elif "sideswipe" in text_lower:
        crash_type = "sideswipe_same"
    elif "head" in text_lower and "on" in text_lower:
        crash_type = "head_on"

    model_map = {
        "rear_end": "sdof",
        "head_on": "sdof",
        "intersection_angle": "impc",
        "sideswipe_same": "sideswipe",
        "sideswipe_opposite": "sideswipe",
    }

    return ExtractionResponse(
        vehicles=vehicles,
        crash_type=crash_type,
        scene=ExtractedScene(road_surface="dry_asphalt", confidence=0.1),
        suggested_model=model_map.get(crash_type, "sdof"),
        raw_extraction={"mock": True, "note": "Set ANTHROPIC_API_KEY for real extraction"},
    )
