"""PDF Processing Module: metadata, page rendering and embedded image export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from pdf_pipeline.exceptions import ExtractionError
from pdf_pipeline.models import EmbeddedImage, PageImage

_MIN_EMBEDDED_IMAGE_PX = 80

# Some producers write these literal strings instead of leaving a field blank.
_PLACEHOLDER_METADATA = {"(anonymous)", "(unspecified)", "(none)", "untitled", "unknown"}


def _clean_metadata_value(value: str | None) -> str:
    cleaned = (value or "").strip()
    return "" if cleaned.lower() in _PLACEHOLDER_METADATA else cleaned


def open_pdf(path: Path) -> fitz.Document:
    try:
        document = fitz.open(path)
    except Exception as error:  # PyMuPDF raises several unrelated exception types
        raise ExtractionError(f"Unable to open {path.name}: {error}") from error

    if document.needs_pass:
        document.close()
        raise ExtractionError(f"{path.name} is password protected")
    return document


def extract_metadata(document: fitz.Document, source: Path) -> dict[str, Any]:
    raw = document.metadata or {}
    return {
        "source_file": source.name,
        "page_count": document.page_count,
        "title": _clean_metadata_value(raw.get("title")),
        "author": _clean_metadata_value(raw.get("author")),
        "subject": _clean_metadata_value(raw.get("subject")),
        "keywords": _clean_metadata_value(raw.get("keywords")),
        "creator": _clean_metadata_value(raw.get("creator")),
        "producer": _clean_metadata_value(raw.get("producer")),
        "creation_date": _clean_metadata_value(raw.get("creationDate")),
        "modification_date": _clean_metadata_value(raw.get("modDate")),
        "is_encrypted": bool(document.is_encrypted),
    }


def native_page_text(document: fitz.Document, page_number: int) -> str:
    """Text from the PDF's own text layer, empty for scanned pages."""
    try:
        return document.load_page(page_number).get_text("text").strip()
    except Exception:
        return ""


def has_text_layer(text: str, threshold: int) -> bool:
    return len(text.replace("\n", "").strip()) >= threshold


def render_page_image(
    document: fitz.Document, page_number: int, output_dir: Path, dpi: int
) -> PageImage:
    """Rasterise a page. PyMuPDF applies the page's /Rotate automatically."""
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    page = document.load_page(page_number)
    pixmap = page.get_pixmap(dpi=dpi)

    image_path = output_dir / f"page_{page_number + 1:04d}.png"
    pixmap.save(image_path)
    return PageImage(
        page_number=page_number + 1,
        path=image_path,
        width=pixmap.width,
        height=pixmap.height,
    )


def extract_embedded_images(
    document: fitz.Document, page_number: int, output_dir: Path
) -> list[EmbeddedImage]:
    """Export figures, diagrams and screenshots embedded in a page."""
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    page = document.load_page(page_number)
    images: list[EmbeddedImage] = []

    for index, image_info in enumerate(page.get_images(full=True)):
        xref = image_info[0]
        try:
            pixmap = fitz.Pixmap(document, xref)
            if pixmap.n - pixmap.alpha >= 4:  # CMYK is not writable as PNG
                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            if pixmap.width < _MIN_EMBEDDED_IMAGE_PX or pixmap.height < _MIN_EMBEDDED_IMAGE_PX:
                continue

            image_path = output_dir / f"page_{page_number + 1:04d}_img_{index + 1:02d}.png"
            pixmap.save(image_path)
            images.append(
                EmbeddedImage(page_number=page_number + 1, index=index + 1, path=image_path)
            )
        except Exception:
            continue  # a single unreadable image must not abort the document

    return images
