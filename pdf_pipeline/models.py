"""Shared data structures passed between pipeline modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

BlockKind = Literal["heading", "paragraph", "list_item", "table", "image_text"]


@dataclass
class OcrLine:
    """A single line of text recognised on an image."""

    text: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass
class PageImage:
    page_number: int
    path: Path
    width: int
    height: int


@dataclass
class EmbeddedImage:
    page_number: int
    index: int
    path: Path


@dataclass
class ExtractedTable:
    page_number: int
    columns: list[str]
    rows: list[list[str]]
    markdown: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "columns": self.columns,
            "rows": self.rows,
            "markdown": self.markdown,
        }


@dataclass
class ContentBlock:
    """One unit of document content in reading order."""

    kind: BlockKind
    page_number: int
    order: float
    text: str = ""
    level: int = 0
    confidence: float | None = None
    source: str = ""
    table: ExtractedTable | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "page_number": self.page_number,
            "order": self.order,
            "source": self.source,
        }
        if self.kind == "table" and self.table is not None:
            payload["table"] = self.table.to_dict()
        else:
            payload["text"] = self.text
        if self.kind == "heading":
            payload["level"] = self.level
        if self.confidence is not None:
            payload["confidence"] = round(self.confidence, 4)
        return payload


@dataclass
class Section:
    """A heading and everything nested beneath it."""

    title: str
    level: int
    blocks: list[ContentBlock] = field(default_factory=list)
    subsections: list["Section"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "level": self.level,
            "blocks": [block.to_dict() for block in self.blocks],
            "subsections": [section.to_dict() for section in self.subsections],
        }


@dataclass
class StructuredDocument:
    """Consolidated result for a single PDF."""

    source_name: str
    metadata: dict[str, Any]
    page_count: int
    blocks: list[ContentBlock] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        declared = str(self.metadata.get("title") or "").strip()
        if declared:
            return declared
        for block in self.blocks:
            if block.kind == "heading" and block.text.strip():
                return block.text.strip()
        return Path(self.source_name).stem

    def plain_text(self) -> str:
        parts = [b.text.strip() for b in self.blocks if b.kind != "table" and b.text.strip()]
        return "\n\n".join(parts)
