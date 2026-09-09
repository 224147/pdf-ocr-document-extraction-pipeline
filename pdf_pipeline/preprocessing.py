"""Image preprocessing with OpenCV to improve OCR accuracy."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from pdf_pipeline.exceptions import ExtractionError

_MAX_DESKEW_ANGLE = 15.0


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ExtractionError(f"Unable to read image: {path}")
    return image


def to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def estimate_skew_angle(gray: np.ndarray) -> float:
    """Estimate page rotation from the minimum-area box around dark pixels."""
    inverted = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(inverted > 0)).astype(np.float32)
    if coords.shape[0] < 50:
        return 0.0

    angle = cv2.minAreaRect(coords)[-1]
    if angle > 45.0:
        angle -= 90.0
    return 0.0 if abs(angle) > _MAX_DESKEW_ANGLE else float(angle)


def deskew(gray: np.ndarray) -> np.ndarray:
    angle = estimate_skew_angle(gray)
    if abs(angle) < 0.1:
        return gray

    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def enhance(gray: np.ndarray) -> np.ndarray:
    """Normalise contrast and suppress scanner noise."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrasted = clahe.apply(gray)
    return cv2.fastNlMeansDenoising(contrasted, None, h=10, templateWindowSize=7, searchWindowSize=21)


def preprocess_for_ocr(
    image: np.ndarray, apply_deskew: bool = True, binarize: bool = False
) -> np.ndarray:
    gray = to_grayscale(image)
    if apply_deskew:
        gray = deskew(gray)
    processed = enhance(gray)
    if binarize:
        processed = cv2.adaptiveThreshold(
            processed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
        )
    return processed
