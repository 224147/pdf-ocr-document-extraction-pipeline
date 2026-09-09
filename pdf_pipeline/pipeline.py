"""Pipeline orchestration for single documents and batches."""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from pdf_pipeline import pdf_processing
from pdf_pipeline.config import PipelineConfig
from pdf_pipeline.consolidation import consolidate
from pdf_pipeline.exceptions import PipelineError
from pdf_pipeline.ingestion import ingest_documents
from pdf_pipeline.models import ContentBlock, StructuredDocument
from pdf_pipeline.ocr import OcrEngine, clean_text, group_lines_into_paragraphs
from pdf_pipeline.output import write_outputs
from pdf_pipeline.preprocessing import load_image, preprocess_for_ocr
from pdf_pipeline.structuring import blocks_from_text_lines, build_sections, promote_ocr_headings
from pdf_pipeline.tables import DoclingAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    source: Path
    document: StructuredDocument | None = None
    markdown_path: Path | None = None
    json_path: Path | None = None
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass
class DocumentExtractionPipeline:
    """Runs the full ingest -> extract -> consolidate -> export workflow."""

    config: PipelineConfig = field(default_factory=PipelineConfig)

    def __post_init__(self) -> None:
        self.config.ensure_directories()
        self._ocr = OcrEngine(
            languages=self.config.ocr_languages,
            use_gpu=self.config.use_gpu,
            confidence_threshold=self.config.ocr_confidence_threshold,
        )
        self._analyzer = DoclingAnalyzer(enable_tables=self.config.enable_tables)

    # ------------------------------------------------------------------ public

    def run(self, inputs) -> list[BatchResult]:
        """Validate, store and process every supplied file or directory."""
        accepted, rejected = ingest_documents(inputs, self.config)
        results = [BatchResult(source=path, error=reason) for path, reason in rejected]

        for stored_path in accepted:
            results.append(self.process(stored_path))
        return results

    def process(self, pdf_path: Path) -> BatchResult:
        started = time.perf_counter()
        result = BatchResult(source=pdf_path)
        try:
            document = self.extract(pdf_path)
            markdown_path, json_path = write_outputs(document, self.config.output_dir)
            result.document = document
            result.markdown_path = markdown_path
            result.json_path = json_path
        except PipelineError as error:
            result.error = str(error)
        except Exception as error:  # never let one document abort a batch
            logger.exception("Unexpected failure processing %s", pdf_path)
            result.error = f"Unexpected error: {error}"
        result.duration_seconds = time.perf_counter() - started
        return result

    def extract(self, pdf_path: Path) -> StructuredDocument:
        document = pdf_processing.open_pdf(pdf_path)
        work_dir = self.config.work_dir / pdf_path.stem
        warnings: list[str] = []

        try:
            metadata = pdf_processing.extract_metadata(document, pdf_path)

            analysis = self._analyzer.analyze(pdf_path)
            warnings.extend(analysis.warnings)
            layout_pages = {b.page_number for b in analysis.blocks if b.kind != "table"}

            text_blocks: list[ContentBlock] = []
            image_blocks: list[ContentBlock] = []

            for index in range(document.page_count):
                page_number = index + 1
                native_text = pdf_processing.native_page_text(document, index)
                digital = pdf_processing.has_text_layer(
                    native_text, self.config.native_text_char_threshold
                )

                if page_number not in layout_pages:
                    text_blocks.extend(
                        self._page_text_blocks(document, index, native_text, digital, warnings)
                    )

                if self.config.enable_image_ocr and digital:
                    image_blocks.extend(self._embedded_image_blocks(document, index, work_dir))

            blocks = consolidate(document.page_count, analysis.blocks, text_blocks, image_blocks)
            blocks = promote_ocr_headings(blocks)

            if self._ocr.init_error:
                warnings.append(self._ocr.init_error)
            if not blocks:
                warnings.append("No content could be extracted from this document")

            return StructuredDocument(
                source_name=pdf_path.name,
                metadata=metadata,
                page_count=document.page_count,
                blocks=blocks,
                sections=build_sections(blocks),
                tables=analysis.tables,
                warnings=warnings,
            )
        finally:
            document.close()
            if not self.config.keep_intermediate_images:
                shutil.rmtree(work_dir, ignore_errors=True)

    # ----------------------------------------------------------------- private

    def _page_text_blocks(
        self,
        document,
        index: int,
        native_text: str,
        digital: bool,
        warnings: list[str],
    ) -> list[ContentBlock]:
        page_number = index + 1

        if digital:
            return blocks_from_text_lines(native_text, page_number)

        try:
            page_image = pdf_processing.render_page_image(
                document, index, self.config.work_dir / f"page_render_{page_number}", self.config.image_dpi
            )
            processed = preprocess_for_ocr(load_image(page_image.path), apply_deskew=self.config.deskew)
            paragraphs = group_lines_into_paragraphs(self._ocr.read(processed))
        except Exception as error:
            warnings.append(f"OCR failed on page {page_number}: {error}")
            return []
        finally:
            if not self.config.keep_intermediate_images:
                shutil.rmtree(self.config.work_dir / f"page_render_{page_number}", ignore_errors=True)

        if not paragraphs and native_text:
            return [
                ContentBlock(
                    kind="paragraph",
                    page_number=page_number,
                    order=0.0,
                    text=clean_text(native_text),
                    source="pdf_text",
                )
            ]

        return [
            ContentBlock(
                kind="paragraph",
                page_number=page_number,
                order=float(position),
                text=text,
                confidence=confidence,
                source="ocr",
            )
            for position, (text, confidence) in enumerate(paragraphs)
        ]

    def _embedded_image_blocks(self, document, index: int, work_dir: Path) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        images = pdf_processing.extract_embedded_images(document, index, work_dir / "images")

        for position, embedded in enumerate(images):
            try:
                lines = self._ocr.read_image_file(embedded.path)
            except Exception:
                continue

            for text, confidence in group_lines_into_paragraphs(lines):
                if len(text) < 3:
                    continue
                blocks.append(
                    ContentBlock(
                        kind="image_text",
                        page_number=index + 1,
                        order=float(position),
                        text=text,
                        confidence=confidence,
                        source=f"image_ocr:{embedded.path.name}",
                    )
                )
        return blocks
