"""Dual-path document ingestion for crash reports.

Police crash reports come in many forms:
1. Typed narrative PDFs (clean text) -> text extraction
2. Scanned forms with checkboxes, handwriting -> OCR + vision model
3. Photos of documents -> vision model
4. Mixed PDFs with text + scanned pages -> hybrid approach

This module handles all of them:
- PyMuPDF (fitz) for text extraction from native PDFs
- Vision-capable LLMs (Claude, GPT-4o) for scanned/image content
- Dual path: try text first, fall back to vision for low-text pages
"""
from __future__ import annotations

import base64
import io
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PageContent:
    """Content extracted from a single page."""
    page_num: int
    text: str = ""
    has_images: bool = False
    image_b64: Optional[str] = None  # base64 PNG of page render
    extraction_method: str = "text"  # text, ocr, vision


@dataclass
class IngestedDocument:
    """Full document after ingestion."""
    filename: str
    pages: List[PageContent] = field(default_factory=list)
    full_text: str = ""
    page_images: List[str] = field(default_factory=list)  # base64 PNGs for vision
    needs_vision: bool = False  # True if scanned/image-heavy pages detected

    @property
    def text_quality(self) -> float:
        """Estimate text extraction quality (0-1). Low = needs vision/OCR."""
        if not self.pages:
            return 0.0
        text_pages = sum(1 for p in self.pages if len(p.text.strip()) > 50)
        return text_pages / len(self.pages)


def ingest_pdf(pdf_bytes: bytes, filename: str = "report.pdf",
               render_dpi: int = 150) -> IngestedDocument:
    """Ingest a PDF using text extraction + page rendering.

    For each page:
    1. Extract text via PyMuPDF
    2. If text is sparse (< 50 chars), render page as image for vision
    3. Return both text and images for downstream processing

    Args:
        pdf_bytes: Raw PDF file bytes
        filename: Original filename
        render_dpi: DPI for page rendering (higher = better OCR, slower)

    Returns:
        IngestedDocument with text and page images
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # Fallback: return raw bytes for vision-only processing
        return _fallback_ingest(pdf_bytes, filename)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: List[PageContent] = []
    page_images: List[str] = []
    text_parts: List[str] = []
    needs_vision = False

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()

        # Render page as image for vision
        mat = fitz.Matrix(render_dpi / 72, render_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Determine if this page needs vision (sparse text = scanned/form)
        is_sparse = len(text) < 50
        has_images = len(page.get_images()) > 0

        if is_sparse:
            needs_vision = True
            method = "vision"
        else:
            method = "text"

        pages.append(PageContent(
            page_num=page_num + 1,
            text=text,
            has_images=has_images or is_sparse,
            image_b64=img_b64,
            extraction_method=method,
        ))

        page_images.append(img_b64)
        text_parts.append(text)

    doc.close()

    return IngestedDocument(
        filename=filename,
        pages=pages,
        full_text="\n\n".join(text_parts),
        page_images=page_images,
        needs_vision=needs_vision,
    )


def ingest_image(image_bytes: bytes, filename: str = "report.jpg") -> IngestedDocument:
    """Ingest a single image (photo of document, diagram, etc.)."""
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")

    return IngestedDocument(
        filename=filename,
        pages=[PageContent(
            page_num=1,
            text="",
            has_images=True,
            image_b64=img_b64,
            extraction_method="vision",
        )],
        full_text="",
        page_images=[img_b64],
        needs_vision=True,
    )


def ingest_text(text: str, filename: str = "report.txt") -> IngestedDocument:
    """Ingest plain text (already extracted or pasted).

    Text is sanitized to mitigate prompt injection before storage.
    """
    sanitized = _sanitize_text(text)
    return IngestedDocument(
        filename=filename,
        pages=[PageContent(page_num=1, text=sanitized, extraction_method="text")],
        full_text=sanitized,
        page_images=[],
        needs_vision=False,
    )


def _fallback_ingest(pdf_bytes: bytes, filename: str) -> IngestedDocument:
    """Fallback when PyMuPDF is not installed - treat entire PDF as image."""
    img_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    return IngestedDocument(
        filename=filename,
        pages=[PageContent(
            page_num=1, text="", has_images=True,
            image_b64=img_b64, extraction_method="vision",
        )],
        full_text="",
        page_images=[img_b64],
        needs_vision=True,
    )


def _sanitize_text(text: str) -> str:
    """Sanitize ingested text to mitigate prompt injection.

    Strips common role markers and instruction-override patterns that
    could confuse the downstream LLM.
    """
    _injection_patterns = [
        re.compile(r'(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)\b'),
        re.compile(r'(?i)\byou\s+are\s+now\b'),
        re.compile(r'(?i)\bnew\s+instructions?\b'),
        re.compile(r'(?i)\bsystem\s*:\s*'),
        re.compile(r'(?i)\bassistant\s*:\s*'),
        re.compile(r'(?i)\bhuman\s*:\s*'),
        re.compile(r'(?i)\b(forget|disregard)\s+(everything|all)\b'),
    ]
    sanitized = text
    for pattern in _injection_patterns:
        sanitized = pattern.sub('[REDACTED]', sanitized)
    if len(sanitized) > 50000:
        sanitized = sanitized[:50000] + "\n[TRUNCATED]"
    return sanitized


def build_extraction_messages(doc: IngestedDocument) -> List[Dict[str, Any]]:
    """Build LLM messages from ingested document.

    For text-rich documents: sends text content
    For scanned/image documents: sends page images with vision
    For mixed: sends both text and images

    Returns messages in the format expected by both Anthropic and OpenAI APIs.
    """
    if not doc.needs_vision:
        # Pure text path - simple and cheap
        return [{
            "role": "user",
            "content": f"Extract all crash data from the following report:\n\n{doc.full_text}",
        }]

    # Vision path - send page images
    content_blocks: List[Dict[str, Any]] = []

    # Add any available text first
    if doc.full_text.strip():
        content_blocks.append({
            "type": "text",
            "text": f"The following text was extracted from the document. Some pages may be scanned or contain forms that aren't captured in the text. I'm also sending page images for those pages.\n\nExtracted text:\n{doc.full_text}",
        })
    else:
        content_blocks.append({
            "type": "text",
            "text": "This crash report is a scanned document. Extract all crash data from the page images below.",
        })

    # Add page images (limit to first 10 pages to manage context)
    for i, page in enumerate(doc.pages[:10]):
        if page.image_b64:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": page.image_b64,
                },
            })

    return [{"role": "user", "content": content_blocks}]


def build_openai_messages(doc: IngestedDocument) -> List[Dict[str, Any]]:
    """Build OpenAI-format messages (slightly different image format)."""
    if not doc.needs_vision:
        return [{
            "role": "user",
            "content": f"Extract all crash data from the following report:\n\n{doc.full_text}",
        }]

    content_blocks: List[Dict[str, Any]] = []

    if doc.full_text.strip():
        content_blocks.append({
            "type": "text",
            "text": f"Extracted text:\n{doc.full_text}\n\nPage images follow for scanned content:",
        })
    else:
        content_blocks.append({
            "type": "text",
            "text": "Extract all crash data from this scanned crash report:",
        })

    for page in doc.pages[:10]:
        if page.image_b64:
            content_blocks.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{page.image_b64}",
                    "detail": "high",
                },
            })

    return [{"role": "user", "content": content_blocks}]
