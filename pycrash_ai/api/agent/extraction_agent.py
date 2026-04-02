"""Crash report extraction agent - powered by Claude or OpenAI.

Takes unstructured text (police reports, witness statements) and extracts
structured crash data using LLM tool_use / function calling.

Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable AI extraction.
Falls back to heuristic extraction without an API key.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pycrash_ai.api.agent.llm_provider import get_provider, LLMResponse
from pycrash_ai.api.agent.tools import ALL_TOOLS
from pycrash_ai.api.agent.ingest import (
    IngestedDocument, ingest_text, ingest_pdf, ingest_image,
    build_extraction_messages, build_openai_messages,
)
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


async def extract_from_text(
    text: str,
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> ExtractionResponse:
    """Extract crash data from text using LLM.

    Args:
        text: Police report or crash description text
        provider_name: "anthropic" or "openai" (auto-detected if None)
        api_key: API key (uses env var if None)
        model: Model override (uses default if None)

    Returns:
        ExtractionResponse with vehicles, crash type, scene data
    """
    provider = get_provider(provider=provider_name, api_key=api_key, model=model)

    if provider.name == "mock":
        return _heuristic_extraction(text)

    response = await provider.complete(
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Extract all crash data from the following report:\n\n{text}",
        }],
        tools=ALL_TOOLS,
    )

    return _parse_response(response)


async def extract_from_document(
    doc: IngestedDocument,
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> ExtractionResponse:
    """Extract crash data from an ingested document (PDF, image, or text).

    Automatically selects text-only or vision path based on document content.
    Scanned PDFs and images use vision-capable models.
    """
    provider = get_provider(provider=provider_name, api_key=api_key, model=model)

    if provider.name == "mock":
        return _heuristic_extraction(doc.full_text)

    # Build appropriate messages based on provider and document type
    if "openai" in provider.name:
        messages = build_openai_messages(doc)
    else:
        messages = build_extraction_messages(doc)

    response = await provider.complete(
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=ALL_TOOLS,
    )

    result = _parse_response(response)
    # Add ingestion metadata
    if result.raw_extraction:
        result.raw_extraction["ingestion"] = {
            "filename": doc.filename,
            "pages": len(doc.pages),
            "text_quality": doc.text_quality,
            "used_vision": doc.needs_vision,
        }
    return result


def _parse_response(response: LLMResponse) -> ExtractionResponse:
    """Parse LLM tool calls into ExtractionResponse."""
    vehicles: List[ExtractedVehicle] = []
    crash_type: Optional[str] = None
    scene: Optional[ExtractedScene] = None
    suggested_model: Optional[str] = None
    raw: Dict[str, Any] = {
        "tool_calls": [{"name": tc.name, "input": tc.input} for tc in response.tool_calls],
        "model": response.model,
        "usage": response.usage,
    }

    for tc in response.tool_calls:
        if tc.name == "extract_vehicle":
            vehicles.append(ExtractedVehicle(
                year=tc.input.get("year"),
                make=tc.input.get("make"),
                model=tc.input.get("model"),
                estimated_speed_mph=tc.input.get("estimated_speed_mph"),
                travel_direction=tc.input.get("travel_direction"),
                role=tc.input.get("role"),
                damage_description=tc.input.get("damage_description"),
                confidence=tc.input.get("confidence", 0.5),
            ))
        elif tc.name == "extract_crash_conditions":
            crash_type = tc.input.get("crash_type")
            suggested_model = tc.input.get("suggested_model")
        elif tc.name == "extract_scene":
            scene = ExtractedScene(
                road_surface=tc.input.get("road_surface"),
                weather=tc.input.get("weather"),
                skid_marks_ft=tc.input.get("skid_marks_vehicle1_ft"),
                speed_limit_mph=tc.input.get("speed_limit_mph"),
                confidence=tc.input.get("confidence", 0.5),
            )

    if response.text:
        raw["text"] = response.text

    return ExtractionResponse(
        vehicles=vehicles,
        crash_type=crash_type,
        scene=scene,
        suggested_model=suggested_model,
        raw_extraction=raw,
    )


def _heuristic_extraction(text: str) -> ExtractionResponse:
    """Heuristic extraction when no API key is set. Useful for testing."""
    text_lower = text.lower()

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
        raw_extraction={"mock": True, "note": "Set ANTHROPIC_API_KEY or OPENAI_API_KEY for AI extraction"},
    )
