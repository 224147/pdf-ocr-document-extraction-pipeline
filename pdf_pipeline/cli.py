"""Command-line interface for the PDF OCR & Document Extraction Pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pdf_pipeline.bootstrap import bootstrap
from pdf_pipeline.config import PipelineConfig
from pdf_pipeline.pipeline import DocumentExtractionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-pipeline",
        description="Extract text, tables and image content from PDFs into Markdown and JSON.",
    )
    parser.add_argument("inputs", nargs="+", help="PDF files or directories containing PDFs")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--storage-dir", type=Path, default=Path("storage/uploads"))
    parser.add_argument("--work-dir", type=Path, default=Path("storage/work"))
    parser.add_argument("--dpi", type=int, default=300, help="Rasterisation DPI for OCR")
    parser.add_argument("--max-size-mb", type=int, default=50)
    parser.add_argument("--languages", default="en", help="Comma separated EasyOCR languages")
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--gpu", action="store_true", help="Enable GPU for EasyOCR")
    parser.add_argument("--no-tables", action="store_true", help="Skip table extraction")
    parser.add_argument("--no-image-ocr", action="store_true", help="Skip OCR of embedded images")
    parser.add_argument("--no-deskew", action="store_true", help="Skip deskew preprocessing")
    parser.add_argument("--keep-images", action="store_true", help="Keep intermediate page images")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> PipelineConfig:
    languages = tuple(part.strip() for part in args.languages.split(",") if part.strip()) or ("en",)
    return PipelineConfig(
        storage_dir=args.storage_dir,
        work_dir=args.work_dir,
        output_dir=args.output_dir,
        max_file_size_mb=args.max_size_mb,
        image_dpi=args.dpi,
        ocr_languages=languages,
        ocr_confidence_threshold=args.min_confidence,
        use_gpu=args.gpu,
        enable_tables=not args.no_tables,
        enable_image_ocr=not args.no_image_ocr,
        deskew=not args.no_deskew,
        keep_intermediate_images=args.keep_images,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    bootstrap()

    pipeline = DocumentExtractionPipeline(config_from_args(args))
    results = pipeline.run(args.inputs)

    failures = 0
    for result in results:
        if result.succeeded and result.document is not None:
            print(
                f"OK   {result.source.name} "
                f"({result.document.page_count} pages, "
                f"{len(result.document.blocks)} blocks, "
                f"{len(result.document.tables)} tables, "
                f"{result.duration_seconds:.1f}s)"
            )
            print(f"     markdown: {result.markdown_path}")
            print(f"     json:     {result.json_path}")
            for warning in result.document.warnings:
                print(f"     warning:  {warning}")
        else:
            failures += 1
            print(f"FAIL {result.source.name}: {result.error}", file=sys.stderr)

    print(f"\nProcessed {len(results) - failures}/{len(results)} document(s) successfully.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
