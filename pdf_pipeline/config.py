"""Runtime configuration for the extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    """Tunable settings shared by every pipeline module."""

    storage_dir: Path = Path("storage/uploads")
    work_dir: Path = Path("storage/work")
    output_dir: Path = Path("output")

    max_file_size_mb: int = 50
    image_dpi: int = 300

    ocr_languages: tuple[str, ...] = ("en",)
    ocr_confidence_threshold: float = 0.30
    use_gpu: bool = False

    enable_tables: bool = True
    enable_image_ocr: bool = True
    deskew: bool = True

    # A page with fewer extractable characters than this is treated as scanned
    # and is routed through OCR instead of the native text layer.
    native_text_char_threshold: int = 120

    keep_intermediate_images: bool = False

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for directory in (self.storage_dir, self.work_dir, self.output_dir):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
