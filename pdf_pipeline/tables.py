"""Table Extraction Module: Docling layout analysis and table structure recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pdf_pipeline.models import ContentBlock, ExtractedTable

_HEADING_LABELS = {"title", "section_header"}
_TEXT_LABELS = {"text", "caption", "footnote", "code", "formula", "checkbox_selected", "checkbox_unselected"}
_SKIP_LABELS = {"page_header", "page_footer", "picture", "chart"}
_MAX_WARNING_LENGTH = 300


def _summarize(error: Exception) -> str:
    """Third-party errors can embed multi-line signed URLs; keep them readable."""
    message = " ".join(str(error).split())
    return message[:_MAX_WARNING_LENGTH] + "..." if len(message) > _MAX_WARNING_LENGTH else message


@dataclass
class DoclingAnalysis:
    blocks: list[ContentBlock] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    markdown: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def pages_covered(self) -> set[int]:
        return {block.page_number for block in self.blocks}


def dataframe_to_markdown(columns: list[str], rows: list[list[str]]) -> str:
    """Render a table as GitHub-flavoured Markdown without extra dependencies."""
    if not columns and not rows:
        return ""

    def escape(cell: str) -> str:
        return cell.replace("|", "\\|").replace("\n", " ").strip()

    header = "| " + " | ".join(escape(str(c)) for c in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(escape(str(cell)) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


class DoclingAnalyzer:
    """Wraps Docling's DocumentConverter with a lazily created converter."""

    def __init__(self, enable_tables: bool = True) -> None:
        self.enable_tables = enable_tables
        self._converter = None
        self._init_error: str | None = None

    def _load_converter(self):
        if self._converter is None and self._init_error is None:
            try:
                from docling.document_converter import DocumentConverter

                self._converter = DocumentConverter()
            except Exception as error:
                self._init_error = f"Docling unavailable: {_summarize(error)}"
        return self._converter

    def analyze(self, path: Path) -> DoclingAnalysis:
        analysis = DoclingAnalysis()
        converter = self._load_converter()
        if converter is None:
            analysis.warnings.append(self._init_error or "Docling unavailable")
            return analysis

        try:
            document = converter.convert(str(path)).document
        except Exception as error:
            analysis.warnings.append(f"Docling conversion failed: {_summarize(error)}")
            return analysis

        try:
            analysis.markdown = document.export_to_markdown()
        except Exception as error:
            analysis.warnings.append(f"Docling markdown export failed: {_summarize(error)}")

        for order, (item, _depth) in enumerate(document.iterate_items()):
            label = str(getattr(item.label, "value", getattr(item, "label", "")))
            if label in _SKIP_LABELS:
                continue

            page_number = _page_of(item)

            if label == "table":
                if not self.enable_tables:
                    continue
                table = self._build_table(item, document, page_number, analysis)
                if table is None:
                    continue
                analysis.tables.append(table)
                analysis.blocks.append(
                    ContentBlock(
                        kind="table",
                        page_number=page_number,
                        order=float(order),
                        table=table,
                        source="docling",
                    )
                )
                continue

            text = str(getattr(item, "text", "") or "").strip()
            if not text:
                continue

            if label in _HEADING_LABELS:
                level = 1 if label == "title" else int(getattr(item, "level", 1) or 1) + 1
                analysis.blocks.append(
                    ContentBlock(
                        kind="heading",
                        page_number=page_number,
                        order=float(order),
                        text=text,
                        level=min(level, 6),
                        source="docling",
                    )
                )
            elif label == "list_item":
                analysis.blocks.append(
                    ContentBlock(
                        kind="list_item",
                        page_number=page_number,
                        order=float(order),
                        text=text,
                        source="docling",
                    )
                )
            elif label in _TEXT_LABELS:
                analysis.blocks.append(
                    ContentBlock(
                        kind="paragraph",
                        page_number=page_number,
                        order=float(order),
                        text=text,
                        source="docling",
                    )
                )

        return analysis

    def _build_table(self, item, document, page_number: int, analysis: DoclingAnalysis):
        try:
            frame = item.export_to_dataframe(document)
        except TypeError:
            frame = item.export_to_dataframe()
        except Exception as error:
            analysis.warnings.append(
                f"Table on page {page_number} could not be parsed: {_summarize(error)}"
            )
            return None

        columns = [str(column) for column in frame.columns]
        rows = [[str(cell) for cell in record] for record in frame.astype(str).values.tolist()]
        if not rows and not columns:
            return None

        return ExtractedTable(
            page_number=page_number,
            columns=columns,
            rows=rows,
            markdown=dataframe_to_markdown(columns, rows),
        )


def _page_of(item) -> int:
    provenance = getattr(item, "prov", None) or []
    if provenance:
        return int(getattr(provenance[0], "page_no", 1) or 1)
    return 1
