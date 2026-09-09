"""Content Structuring Module: heading detection and section hierarchy."""

from __future__ import annotations

import re

from pdf_pipeline.models import ContentBlock, Section
from pdf_pipeline.ocr import clean_text

_NUMBERED = re.compile(r"^(\d+(\.\d+)*)[.)]?\s+\S")
_SENTENCE_END = re.compile(r"[.!?;:,]$")
_BULLET = re.compile(r"^[-*\u2022\u25cf\u00b7\u25aa]\s+")
# A line ending like this is wrapped text, so the next line continues it.
_CONTINUES = re.compile(r"([,/&\-]|\b(and|or|with|of|the|to|for|in|using))$", re.IGNORECASE)
_MAX_HEADING_WORDS = 9


def looks_like_heading(text: str) -> bool:
    """Heuristic used for OCR output, which carries no layout labels."""
    stripped = text.strip()
    if not stripped or len(stripped) > 80 or "\n" in stripped:
        return False
    if not stripped[0].isalnum():  # bullets and wingding glyphs are not headings
        return False
    if _SENTENCE_END.search(stripped):
        return False

    words = stripped.split()
    if len(words) > _MAX_HEADING_WORDS:
        return False
    if _NUMBERED.match(stripped):
        return True

    letters = [char for char in stripped if char.isalpha()]
    if letters and all(char.isupper() for char in letters):
        return True
    return stripped.istitle() and len(words) <= 6


def infer_heading_level(text: str) -> int:
    match = _NUMBERED.match(text.strip())
    if match:
        return min(match.group(1).count(".") + 2, 6)
    return 2


def promote_ocr_headings(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """Convert OCR paragraphs that look like headings into heading blocks."""
    for block in blocks:
        if block.source.startswith("ocr") and block.kind == "paragraph" and looks_like_heading(block.text):
            block.kind = "heading"
            block.level = infer_heading_level(block.text)
    return blocks


def blocks_from_text_lines(text: str, page_number: int) -> list[ContentBlock]:
    """Turn a page's native text layer into headings, list items and paragraphs."""
    blocks: list[ContentBlock] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            blocks.append(
                ContentBlock(
                    kind="paragraph",
                    page_number=page_number,
                    order=float(len(blocks)),
                    text=clean_text(" ".join(buffer)),
                    source="pdf_text",
                )
            )
            buffer.clear()

    for raw_line in text.splitlines():
        line = clean_text(raw_line)
        if not line:
            flush()
        elif looks_like_heading(line) and not (buffer and _CONTINUES.search(buffer[-1])):
            flush()
            blocks.append(
                ContentBlock(
                    kind="heading",
                    page_number=page_number,
                    order=float(len(blocks)),
                    text=line,
                    level=infer_heading_level(line),
                    source="pdf_text",
                )
            )
        elif _BULLET.match(line):
            flush()
            blocks.append(
                ContentBlock(
                    kind="list_item",
                    page_number=page_number,
                    order=float(len(blocks)),
                    text=_BULLET.sub("", line),
                    source="pdf_text",
                )
            )
        else:
            buffer.append(line)

    flush()
    return [block for block in blocks if block.text]


def build_sections(blocks: list[ContentBlock]) -> list[Section]:
    """Nest content under its closest preceding heading."""
    root: list[Section] = []
    stack: list[Section] = []

    for block in blocks:
        if block.kind == "heading":
            section = Section(title=block.text, level=max(block.level, 1))
            while stack and stack[-1].level >= section.level:
                stack.pop()
            if stack:
                stack[-1].subsections.append(section)
            else:
                root.append(section)
            stack.append(section)
            continue

        if not stack:
            preamble = Section(title="Document", level=1)
            root.append(preamble)
            stack.append(preamble)
        stack[-1].blocks.append(block)

    return root
