"""Extraction API routes - AI-powered crash report parsing.

Supports:
- Plain text input (POST JSON body)
- PDF file upload (POST multipart/form-data)
- Image file upload (POST multipart/form-data)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Header, UploadFile

from crashout.models import ExtractionRequest, ExtractionResponse
from crashout.agent.extraction_agent import extract_from_text, extract_from_document
from crashout.agent.ingest import ingest_pdf, ingest_image, ingest_text

router = APIRouter()


@router.post("/extract", response_model=ExtractionResponse)
async def extract_from_text_input(
    req: ExtractionRequest,
    x_provider: Optional[str] = Header(None, description="LLM provider: 'anthropic' or 'openai'"),
    x_api_key: Optional[str] = Header(None, description="API key (overrides env var)"),
    x_model: Optional[str] = Header(None, description="Model override"),
):
    """Extract crash data from text.

    For plain text / pasted police report narratives.
    For PDF or image files, use /extract/upload instead.
    """
    return await extract_from_text(
        text=req.text,
        provider_name=x_provider,
        api_key=x_api_key,
        model=x_model,
    )


@router.post("/extract/upload", response_model=ExtractionResponse)
async def extract_from_file(
    file: UploadFile = File(..., description="PDF or image file (crash report)"),
    x_provider: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    x_model: Optional[str] = Header(None),
):
    """Extract crash data from an uploaded PDF or image.

    Dual-path ingestion:
    - Text-rich PDFs: extracts text directly (fast, cheap)
    - Scanned PDFs / images: renders pages and uses vision model (slower, handles forms/handwriting)
    - Mixed PDFs: uses both text + vision for best results

    Supported formats: .pdf, .png, .jpg, .jpeg, .tiff, .bmp
    """
    content = await file.read()
    filename = file.filename or "upload"

    # Determine file type and ingest
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        doc = ingest_pdf(content, filename)
    elif ext in ("png", "jpg", "jpeg", "tiff", "bmp", "webp"):
        doc = ingest_image(content, filename)
    else:
        # Try as text
        try:
            text = content.decode("utf-8")
            doc = ingest_text(text, filename)
        except UnicodeDecodeError:
            # Binary file, try as PDF
            doc = ingest_pdf(content, filename)

    return await extract_from_document(
        doc=doc,
        provider_name=x_provider,
        api_key=x_api_key,
        model=x_model,
    )
