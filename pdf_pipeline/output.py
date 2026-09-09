"""Output Generation Module: Markdown and JSON serialisation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pdf_pipeline.models import StructuredDocument


def render_markdown(document: StructuredDocument) -> str:
    lines: list[str] = [f"# {document.title}", ""]

    metadata_rows = [(key, value) for key, value in document.metadata.items() if value not in ("", None)]
    if metadata_rows:
        lines.extend(["## Document Metadata", ""])
        lines.extend(f"- **{key.replace('_', ' ').title()}:** {value}" for key, value in metadata_rows)
        lines.append("")

    current_page = None
    for block in document.blocks:
        if block.page_number != current_page:
            current_page = block.page_number
            lines.extend([f"<!-- page {current_page} -->", ""])

        if block.kind == "heading":
            lines.extend([f"{'#' * min(max(block.level, 1), 6)} {block.text}", ""])
        elif block.kind == "list_item":
            lines.extend([f"- {block.text}", ""])
        elif block.kind == "table" and block.table is not None:
            lines.extend([block.table.markdown, ""])
        elif block.kind == "image_text":
            lines.extend([f"> **Image text:** {block.text}", ""])
        elif block.text:
            lines.extend([block.text, ""])

    if document.warnings:
        lines.extend(["---", "", "## Processing Warnings", ""])
        lines.extend(f"- {warning}" for warning in document.warnings)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def document_to_dict(document: StructuredDocument) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_name": document.source_name,
        "title": document.title,
        "page_count": document.page_count,
        "metadata": document.metadata,
        "content_blocks": [block.to_dict() for block in document.blocks],
        "sections": [section.to_dict() for section in document.sections],
        "tables": [table.to_dict() for table in document.tables],
        "plain_text": document.plain_text(),
        "warnings": document.warnings,
    }


def write_outputs(document: StructuredDocument, output_dir: Path) -> tuple[Path, Path]:
    """Write <stem>.md and <stem>.json with owner-only permissions."""
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stem = Path(document.source_name).stem

    markdown_path = output_dir / f"{stem}.md"
    markdown_path.write_text(render_markdown(document), encoding="utf-8")
    markdown_path.chmod(0o600)

    json_path = output_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(document_to_dict(document), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    json_path.chmod(0o600)

    return markdown_path, json_path
