"""Compare the learned display crop with the legacy crop on one image.

Usage (from the repository root)::

    .venv/bin/python backend/validation/test.py backend/data/captures/example.jpg

The output image marks the crop.pt display box in blue, legacy HSV crop in
yellow, crop.pt-path digit boxes in green, and legacy-path digit boxes in red.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
CV_SOURCE = (
    REPOSITORY_ROOT / "new_system" / "Digit_QRCode_Detection" / "backend" / "src"
)
SERVICE_SOURCE = BACKEND_ROOT / "src"
if str(CV_SOURCE) not in sys.path:
    sys.path.insert(0, str(CV_SOURCE))
if str(SERVICE_SOURCE) not in sys.path:
    sys.path.insert(0, str(SERVICE_SOURCE))

from backend.cv.digit_detector import DigitDetector  # noqa: E402
from backend.cv.display_locator import DisplayRegion  # noqa: E402
from roll_qr_scale.crop_digit_detector import CropModelDigitDetector  # noqa: E402


def load_backend_env() -> None:
    """Read backend/.env without overriding explicitly exported variables."""
    env_path = BACKEND_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def project_path(value: str, default: Path) -> Path:
    raw = value.strip() if value else ""
    path = Path(raw).expanduser() if raw else default
    if path.is_absolute():
        return path.resolve()
    # The app accepts paths relative to the repo or backend working directory.
    for base in (BACKEND_ROOT, REPOSITORY_ROOT, Path.cwd()):
        candidate = (base / path).resolve()
        if candidate.is_file():
            return candidate
    return (BACKEND_ROOT / path).resolve()


def draw_box(
    image: np.ndarray,
    xyxy: tuple[float, float, float, float],
    color: tuple[int, int, int],
    label: str,
    *,
    thickness: int = 2,
) -> None:
    x1, y1, x2, y2 = (int(round(value)) for value in xyxy)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    font_scale = max(0.45, min(0.8, image.shape[1] / 1400))
    (text_width, text_height), baseline = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2
    )
    top = max(text_height + baseline + 4, y1)
    cv2.rectangle(
        image,
        (x1, top - text_height - baseline - 4),
        (x1 + text_width + 6, top),
        color,
        cv2.FILLED,
    )
    cv2.putText(
        image,
        label,
        (x1 + 3, top - baseline - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def annotate(
    image: np.ndarray,
    model_region: DisplayRegion | None,
    model_digits: list[Any],
    legacy_region: DisplayRegion | None,
    legacy_digits: list[Any],
) -> np.ndarray:
    output = image.copy()
    if model_region:
        draw_box(
            output,
            (model_region.x1, model_region.y1, model_region.x2, model_region.y2),
            (255, 120, 0),
            "crop.pt ROI",
            thickness=3,
        )
        for digit in model_digits:
            box = digit.box
            draw_box(
                output,
                (box.x, box.y, box.x + box.width, box.y + box.height),
                (40, 190, 40),
                str(digit.value),
            )
    if legacy_region:
        draw_box(
            output,
            (legacy_region.x1, legacy_region.y1, legacy_region.x2, legacy_region.y2),
            (0, 220, 255),
            "legacy HSV ROI",
            thickness=2,
        )
        for digit in legacy_digits:
            box = digit.box
            draw_box(
                output,
                (box.x, box.y, box.x + box.width, box.y + box.height),
                (30, 30, 230),
                str(digit.value),
            )
    legend = "crop.pt ROI / digits: blue-green    HSV ROI / digits: yellow-red"
    cv2.putText(
        output,
        legend,
        (12, max(24, output.shape[0] - 14)),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.45, min(0.7, output.shape[1] / 1600)),
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return output


def main() -> int:
    load_backend_env()
    parser = argparse.ArgumentParser(
        description="Compare crop.pt and legacy display crops on one image."
    )
    parser.add_argument("image", type=Path, help="Input image path")
    parser.add_argument(
        "--output",
        type=Path,
        help="Annotated output path (defaults to backend/validation/output/<name>_annotated.jpg)",
    )
    parser.add_argument(
        "--crop-padding",
        type=float,
        default=float(os.environ.get("ROLL_SCALE_CROP_DIGIT_PADDING", "0.12")),
        help="Fractional padding added around crop.pt box before digit detection",
    )
    parser.add_argument(
        "--crop-confidence",
        type=float,
        default=float(os.environ.get("ROLL_SCALE_CROP_DIGIT_CONFIDENCE", "0.001")),
    )
    parser.add_argument(
        "--crop-image-size",
        type=int,
        default=int(os.environ.get("ROLL_SCALE_CROP_DIGIT_IMAGE_SIZE", "640")),
    )
    parser.add_argument(
        "--digit-confidence",
        type=float,
        default=float(os.environ.get("ROLL_SCALE_DIGIT_CONFIDENCE", "0.2")),
    )
    parser.add_argument(
        "--digit-image-size",
        type=int,
        default=int(os.environ.get("ROLL_SCALE_DIGIT_IMAGE_SIZE", "736")),
    )
    parser.add_argument(
        "--display-colors",
        default=os.environ.get("ROLL_SCALE_DISPLAY_COLORS", "red"),
    )
    args = parser.parse_args()

    source_path = args.image.expanduser().resolve()
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is None:
        parser.error(f"could not read image: {source_path}")

    crop_model_path = project_path(
        os.environ.get("ROLL_SCALE_CROP_DIGIT_MODEL", ""),
        BACKEND_ROOT / "model" / "crop.pt",
    )
    digit_model_path = project_path(
        os.environ.get("ROLL_SCALE_DIGIT_MODEL", ""),
        BACKEND_ROOT / "model" / "best.pt",
    )
    for model_path in (crop_model_path, digit_model_path):
        if not model_path.is_file():
            parser.error(f"model file not found: {model_path}")
    if args.crop_padding < 0:
        parser.error("--crop-padding must be non-negative")

    cv2.setNumThreads(1)
    crop_detector = CropModelDigitDetector(
        digit_model_path,
        crop_model_path,
        args.digit_confidence,
        crop_confidence=args.crop_confidence,
        crop_image_size=args.crop_image_size,
        crop_padding=args.crop_padding,
        display_colors=tuple(
            value.strip().lower()
            for value in args.display_colors.split(",")
            if value.strip()
        ),
        image_size=args.digit_image_size,
        prefer_top_row=True,
        cpu_threads=max(1, min(2, (os.cpu_count() or 2) // 2)),
    )

    model_run = crop_detector.detect_with_details(image)
    model_region = model_run.display
    model_score = model_region.locator_score if model_region else None
    model_digits = model_run.digits

    # Run the actual production legacy crop search (candidate ranking,
    # scale variants, confidence filtering, and optional sharpening).
    legacy_run = DigitDetector.detect_with_details(crop_detector, image)
    legacy_region = legacy_run.display
    legacy_digits = legacy_run.digits

    output = annotate(
        image,
        model_region,
        model_digits,
        legacy_region,
        legacy_digits,
    )
    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else BACKEND_ROOT
        / "validation"
        / "output"
        / f"{source_path.stem}_annotated.jpg"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), output):
        raise OSError(f"could not write annotated image: {output_path}")

    model_reading = "".join(str(item.value) for item in model_digits) or "unread"
    legacy_reading = "".join(str(item.value) for item in legacy_digits) or "unread"
    print(f"Input: {source_path} ({image.shape[1]}x{image.shape[0]})")
    print(
        f"crop.pt: classes={crop_detector.crop_model.names!r}, "
        f"confidence-threshold={crop_detector.crop_confidence}"
    )
    print(
        f"crop.pt ROI: {model_region.bbox if model_region else 'not found'}; confidence={model_score}"
    )
    print(f"crop.pt ROI digits: {model_reading}")
    print(f"Legacy HSV ROI: {legacy_region.bbox if legacy_region else 'not found'}")
    print(f"Legacy HSV digits: {legacy_reading}")
    print(f"Annotated image: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
