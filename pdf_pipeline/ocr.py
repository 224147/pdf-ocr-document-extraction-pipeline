"""OCR Processing Module: EasyOCR recognition plus text normalisation."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np

from pdf_pipeline.models import OcrLine

_WHITESPACE = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Normalise unicode, ligatures and whitespace produced by OCR."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _CONTROL.sub("", normalized)
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = _WHITESPACE.sub(" ", normalized)
    normalized = _BLANK_LINES.sub("\n\n", normalized)
    return normalized.strip()


class OcrEngine:
    """Lazily initialised EasyOCR reader shared across documents."""

    def __init__(
        self,
        languages: tuple[str, ...] = ("en",),
        use_gpu: bool = False,
        confidence_threshold: float = 0.30,
    ) -> None:
        self.languages = list(languages)
        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold
        self._reader = None
        self._init_error: str | None = None

    @property
    def available(self) -> bool:
        return self._load_reader() is not None

    @property
    def init_error(self) -> str | None:
        return self._init_error

    def _load_reader(self):
        if self._reader is None and self._init_error is None:
            try:
                import easyocr

                self._reader = easyocr.Reader(self.languages, gpu=self.use_gpu, verbose=False)
            except Exception as error:  # model download or torch failure
                self._init_error = f"EasyOCR unavailable: {error}"
        return self._reader

    def read(self, image: np.ndarray) -> list[OcrLine]:
        reader = self._load_reader()
        if reader is None:
            return []

        try:
            raw_results = reader.readtext(image, detail=1, paragraph=False)
        except Exception as error:
            self._init_error = f"OCR failed: {error}"
            return []

        lines: list[OcrLine] = []
        for box, text, confidence in raw_results:
            cleaned = clean_text(str(text))
            if not cleaned or float(confidence) < self.confidence_threshold:
                continue
            xs = [int(point[0]) for point in box]
            ys = [int(point[1]) for point in box]
            lines.append(
                OcrLine(
                    text=cleaned,
                    confidence=float(confidence),
                    bbox=(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)),
                )
            )
        return lines

    def read_image_file(self, path: Path) -> list[OcrLine]:
        from pdf_pipeline.preprocessing import load_image, preprocess_for_ocr

        return self.read(preprocess_for_ocr(load_image(path)))


def group_lines_into_paragraphs(lines: list[OcrLine]) -> list[tuple[str, float]]:
    """Merge recognised lines into reading-order paragraphs with mean confidence.

    Lines are split apart on a vertical gap or on a noticeable change in text
    height, which is what separates a heading from the body text under it.
    """
    if not lines:
        return []

    ordered = sorted(lines, key=lambda line: (line.bbox[1], line.bbox[0]))
    paragraphs: list[tuple[str, float]] = []
    buffer: list[OcrLine] = [ordered[0]]

    for previous, current in zip(ordered, ordered[1:]):
        previous_height = max(previous.bbox[3], 1)
        current_height = max(current.bbox[3], 1)
        reference = min(previous_height, current_height)
        gap = current.bbox[1] - (previous.bbox[1] + previous.bbox[3])
        size_ratio = max(previous_height, current_height) / reference

        if gap > reference * 0.9 or size_ratio > 1.35:
            paragraphs.append(_flush(buffer))
            buffer = [current]
        else:
            buffer.append(current)

    paragraphs.append(_flush(buffer))
    return [item for item in paragraphs if item[0]]


def _flush(buffer: list[OcrLine]) -> tuple[str, float]:
    text = clean_text(" ".join(line.text for line in buffer))
    confidence = float(np.mean([line.confidence for line in buffer])) if buffer else 0.0
    return text, confidence
