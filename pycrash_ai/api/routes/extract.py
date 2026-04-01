"""Extraction API routes - AI-powered crash report parsing."""
from __future__ import annotations

from fastapi import APIRouter

from pycrash_ai.api.models import ExtractionRequest, ExtractionResponse
from pycrash_ai.api.agent.extraction_agent import extract_from_text

router = APIRouter()


@router.post("/extract", response_model=ExtractionResponse)
async def extract_crash_data(req: ExtractionRequest):
    """Extract structured crash data from a police report or description.

    Uses Claude AI to parse unstructured text and extract:
    - Vehicle information (make, model, speed, direction, damage)
    - Crash conditions (type, angle, closing speed)
    - Scene data (road surface, weather, friction)

    Set ANTHROPIC_API_KEY env var for AI extraction.
    Without it, returns mock data for testing.
    """
    return await extract_from_text(req.text)
