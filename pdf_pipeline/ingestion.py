"""Document Upload Module: validation and secure storage of incoming PDFs."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Iterable

from pdf_pipeline.config import PipelineConfig
from pdf_pipeline.exceptions import DocumentValidationError

PDF_MAGIC = b"%PDF-"
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_MAX_NAME_LENGTH = 100


def sanitize_filename(name: str) -> str:
    """Reduce an arbitrary upload name to a safe, traversal-free basename."""
    base = Path(name).name
    base = _UNSAFE_CHARS.sub("_", base).lstrip(".")
    stem, _, suffix = base.rpartition(".")
    if not stem:
        stem, suffix = base or "document", "pdf"
    return f"{stem[:_MAX_NAME_LENGTH]}.{suffix.lower() or 'pdf'}"


def validate_pdf(path: Path, max_size_bytes: int) -> None:
    """Validate extension, size and magic bytes before any parsing happens."""
    if not path.exists() or not path.is_file():
        raise DocumentValidationError(f"File not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise DocumentValidationError(f"Unsupported format '{path.suffix}': only .pdf is accepted")

    size = path.stat().st_size
    if size == 0:
        raise DocumentValidationError(f"File is empty: {path.name}")
    if size > max_size_bytes:
        limit_mb = max_size_bytes / (1024 * 1024)
        raise DocumentValidationError(
            f"File {path.name} is {size / (1024 * 1024):.1f} MB, exceeding the {limit_mb:.0f} MB limit"
        )

    with path.open("rb") as handle:
        if handle.read(len(PDF_MAGIC)) != PDF_MAGIC:
            raise DocumentValidationError(f"File {path.name} is not a valid PDF (bad header)")


def store_document(path: Path, storage_dir: Path) -> Path:
    """Copy a validated PDF into private storage under a sanitized name."""
    storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    safe_name = sanitize_filename(path.name)
    destination = storage_dir / f"{Path(safe_name).stem}_{digest}.pdf"

    # Defence in depth: the resolved target must stay inside the storage root.
    root = storage_dir.resolve()
    if not destination.resolve().is_relative_to(root):
        raise DocumentValidationError(f"Refusing to write outside storage root: {destination}")

    if not destination.exists():
        shutil.copy2(path, destination)
    destination.chmod(0o600)
    return destination


def collect_pdf_paths(inputs: Iterable[str | Path]) -> list[Path]:
    """Expand files and directories into a sorted list of candidate PDFs."""
    resolved: list[Path] = []
    for entry in inputs:
        candidate = Path(entry).expanduser()
        if candidate.is_dir():
            resolved.extend(sorted(candidate.glob("*.pdf")))
        else:
            resolved.append(candidate)
    return resolved


def ingest_documents(
    inputs: Iterable[str | Path], config: PipelineConfig
) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Validate and store every input, returning accepted paths and rejections."""
    accepted: list[Path] = []
    rejected: list[tuple[Path, str]] = []

    for candidate in collect_pdf_paths(inputs):
        try:
            validate_pdf(candidate, config.max_file_size_bytes)
            accepted.append(store_document(candidate, config.storage_dir))
        except DocumentValidationError as error:
            rejected.append((candidate, str(error)))

    return accepted, rejected
