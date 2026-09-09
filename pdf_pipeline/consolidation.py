"""Content Consolidation Module: merge layout, OCR and image text into one flow."""

from __future__ import annotations

from collections import defaultdict

from pdf_pipeline.models import ContentBlock


def _by_page(blocks: list[ContentBlock]) -> dict[int, list[ContentBlock]]:
    grouped: dict[int, list[ContentBlock]] = defaultdict(list)
    for block in blocks:
        grouped[block.page_number].append(block)
    return grouped


def consolidate(
    page_count: int,
    layout_blocks: list[ContentBlock],
    ocr_blocks: list[ContentBlock],
    image_blocks: list[ContentBlock],
) -> list[ContentBlock]:
    """Build a single page-ordered stream, preferring layout data over raw OCR.

    OCR output is used for a page whenever layout analysis produced nothing for
    it, which is what happens with scanned or image-only pages.
    """
    layout_by_page = _by_page(layout_blocks)
    ocr_by_page = _by_page(ocr_blocks)
    images_by_page = _by_page(image_blocks)

    merged: list[ContentBlock] = []
    for page_number in range(1, page_count + 1):
        page_layout = sorted(layout_by_page.get(page_number, []), key=lambda b: b.order)
        page_text = [b for b in page_layout if b.kind != "table"]

        if page_text:
            page_blocks = page_layout
        else:
            # Keep any tables Docling found even when its text extraction was empty.
            page_blocks = sorted(
                ocr_by_page.get(page_number, []) + [b for b in page_layout if b.kind == "table"],
                key=lambda b: b.order,
            )

        page_blocks.extend(sorted(images_by_page.get(page_number, []), key=lambda b: b.order))
        merged.extend(page_blocks)

    for position, block in enumerate(merged):
        block.order = float(position)
    return merged
