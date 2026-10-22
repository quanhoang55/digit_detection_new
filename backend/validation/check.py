"""Validate and visually inspect the YOLO crop/label dataset.

Run from the repository root::

    .venv/bin/python backend/validation/check.py
    .venv/bin/python backend/validation/check.py --check-only

Images and labels are paired by filename stem. In the viewer, press N/Right
for next, P/Left for previous, and Q/Esc to close. This tool never modifies
the dataset.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent / "data"
IMAGE_DIR = ROOT / "data"
LABEL_DIR = ROOT / "label"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
CLASS_NAMES = ["-", ".", *map(str, range(10))]


def collect_by_stem(folder: Path, suffixes: set[str]) -> dict[str, Path]:
    if not folder.is_dir():
        return {}
    return {
        path.stem.casefold(): path
        for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold())
        if path.is_file() and path.suffix.lower() in suffixes
    }


def parse_labels(
    path: Path,
) -> tuple[list[tuple[int, float, float, float, float]], list[str]]:
    boxes = []
    errors = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        return [], [f"could not read label: {exc}"]

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            errors.append(f"line {line_number}: expected 5 values, got {len(fields)}")
            continue
        try:
            class_value = float(fields[0])
            values = [float(value) for value in fields[1:]]
        except ValueError:
            errors.append(f"line {line_number}: values must be numeric")
            continue
        if not math.isfinite(class_value) or not class_value.is_integer():
            errors.append(f"line {line_number}: class id must be an integer")
            continue
        class_id = int(class_value)
        if class_id < 0 or class_id >= len(CLASS_NAMES):
            errors.append(f"line {line_number}: class id {class_id} is outside 0..11")
            continue
        if not all(math.isfinite(value) for value in values):
            errors.append(f"line {line_number}: coordinates must be finite numbers")
            continue
        x_center, y_center, width, height = values
        if width <= 0 or height <= 0:
            errors.append(f"line {line_number}: box width and height must be positive")
            continue
        if not all(0 <= value <= 1 for value in values):
            errors.append(
                f"line {line_number}: normalized coordinates must be in [0, 1]"
            )
            continue
        if x_center - width / 2 < -1e-6 or x_center + width / 2 > 1 + 1e-6:
            errors.append(
                f"line {line_number}: box extends beyond left/right image edge"
            )
            continue
        if y_center - height / 2 < -1e-6 or y_center + height / 2 > 1 + 1e-6:
            errors.append(
                f"line {line_number}: box extends beyond top/bottom image edge"
            )
            continue
        boxes.append((class_id, x_center, y_center, width, height))
    return boxes, errors


def draw_review(image, boxes, title: str):
    height, width = image.shape[:2]
    # Fit the whole image on screen, but enlarge small display crops so their
    # character boxes and labels are actually inspectable.
    scale = min(3.0, 1100 / width, 800 / height)
    shown_width = max(1, round(width * scale))
    shown_height = max(1, round(height * scale))
    canvas = cv2.resize(
        image,
        (shown_width, shown_height),
        interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
    )
    for class_id, x_center, y_center, box_width, box_height in boxes:
        x1 = round((x_center - box_width / 2) * width * scale)
        y1 = round((y_center - box_height / 2) * height * scale)
        x2 = round((x_center + box_width / 2) * width * scale)
        y2 = round((y_center + box_height / 2) * height * scale)
        color = (0, 255, 0)
        thickness = max(2, round(2 * min(scale, 1.5)))
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
        label = CLASS_NAMES[class_id]
        font_scale = max(0.7, min(1.4, 0.7 * scale))
        (text_width, text_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2
        )
        label_top = max(text_height + baseline + 8, y1)
        cv2.rectangle(
            canvas,
            (x1, label_top - text_height - baseline - 8),
            (x1 + text_width + 10, label_top),
            (20, 20, 20),
            cv2.FILLED,
        )
        cv2.putText(
            canvas,
            label,
            (x1 + 5, label_top - baseline - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=IMAGE_DIR)
    parser.add_argument("--labels", type=Path, default=LABEL_DIR)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate files without opening the image viewer",
    )
    args = parser.parse_args()

    images = collect_by_stem(args.images, IMAGE_EXTENSIONS)
    labels = collect_by_stem(args.labels, {".txt"})
    if not images and not labels:
        parser.error(
            f"no image or label files found in {args.images} and {args.labels}"
        )

    issues = 0
    for stem in sorted(images.keys() - labels.keys()):
        print(f"MISSING LABEL: {images[stem].name}")
        issues += 1
    for stem in sorted(labels.keys() - images.keys()):
        print(f"MISSING IMAGE: {labels[stem].name}")
        issues += 1

    review_items = []
    for stem in sorted(images.keys() & labels.keys()):
        image_path, label_path = images[stem], labels[stem]
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            print(f"INVALID IMAGE: {image_path}")
            issues += 1
            continue
        boxes, errors = parse_labels(label_path)
        for error in errors:
            print(f"INVALID LABEL: {label_path.name}: {error}")
            issues += 1
        if not errors:
            print(f"OK: {image_path.name} ↔ {label_path.name} ({len(boxes)} boxes)")
        review_items.append((image_path, image, boxes, errors))

    print(
        f"Checked {len(images)} images and {len(labels)} labels; "
        f"{issues} issue(s), {len(review_items)} matched pair(s)."
    )

    if not args.check_only and review_items:
        index = 0
        window = "YOLO dataset label check"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        while True:
            image_path, image, boxes, errors = review_items[index]
            status = (
                "INVALID LABEL - see terminal" if errors else f"{len(boxes)} label(s)"
            )
            title = (
                f"{index + 1}/{len(review_items)} {image_path.name} | {status} | "
                "N/Right next, P/Left previous, Q/Esc close"
            )
            cv2.setWindowTitle(window, title)
            cv2.imshow(window, draw_review(image, boxes, title))
            key = cv2.waitKeyEx(0)
            low_key = key & 0xFF
            if low_key in (ord("q"), 27):
                break
            if low_key in (ord("n"), 83) or key == 2555904:
                index = (index + 1) % len(review_items)
            elif low_key in (ord("p"), 81) or key == 2424832:
                index = (index - 1) % len(review_items)
        cv2.destroyAllWindows()

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
