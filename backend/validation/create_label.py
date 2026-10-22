"""Auto-create digit YOLO labels from display crops located by crop.pt.

Usage from the repository root::

    .venv/bin/python backend/validation/create_label.py backend/data/captures
    .venv/bin/python backend/validation/create_label.py backend/data/captures --recursive

For each source image, crop.pt locates the display, then best.pt predicts the
characters in that crop. The clean crop is saved under
backend/validation/data/data and best.pt's automatic detections are saved as
YOLO labels under backend/validation/data/label.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
CV_SOURCE = (
    REPOSITORY_ROOT / "new_system" / "Digit_QRCode_Detection" / "backend" / "src"
)
if str(CV_SOURCE) not in sys.path:
    sys.path.insert(0, str(CV_SOURCE))

from backend.cv.display_locator import DisplayRegion  # noqa: E402

OUTPUT_ROOT = Path(__file__).resolve().parent / "data"
IMAGE_OUTPUT = OUTPUT_ROOT / "data"
LABEL_OUTPUT = OUTPUT_ROOT / "label"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
EXPECTED_CLASSES = {
    index: symbol for index, symbol in enumerate(["-", ".", *map(str, range(10))])
}


class LabelReview:
    """Review and edit predicted character boxes on one display crop."""

    WINDOW = "Review auto labels"
    MAX_PREVIEW_EDGE = 800

    def __init__(
        self, image, crop_bounds, prediction, names: dict[int, str], image_name: str
    ):
        self.image = image
        self.names = names
        self.image_name = image_name
        self.image_height, self.image_width = image.shape[:2]
        self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2 = crop_bounds
        self.width = self.crop_x2 - self.crop_x1
        self.height = self.crop_y2 - self.crop_y1
        self.scale = min(
            1.0, self.MAX_PREVIEW_EDGE / max(self.image_width, self.image_height)
        )
        self.preview_width = max(1, round(self.image_width * self.scale))
        self.preview_height = max(1, round(self.image_height * self.scale))
        self.boxes: list[list[int]] = []
        if prediction.boxes is not None:
            for coords, class_id in zip(
                prediction.boxes.xyxy.tolist(),
                prediction.boxes.cls.tolist(),
                strict=True,
            ):
                x1, y1, x2, y2 = map(int, map(round, coords))
                self.boxes.append([int(class_id), x1, y1, x2, y2])
        self.selected: int | None = None
        self.current_class = 2
        self.drag_start: tuple[int, int] | None = None
        self.drag_mode: str | None = None
        self.original_box: list[int] | None = None
        self.resize_anchor: tuple[int, int] | None = None
        self.preview_cursor: tuple[int, int] | None = None
        self.add_mode = True
        self.notice = "Add mode: drag to draw a box, including over a prediction."

    def _image_point(self, x: int, y: int) -> tuple[int, int]:
        # Convert callback coordinates using the actual image area in the
        # resizable OpenCV window (not its title bar or OS scaling factor).
        shown_width, shown_height = self.preview_width, self.preview_height
        try:
            _left, _top, actual_width, actual_height = cv2.getWindowImageRect(
                self.WINDOW
            )
            if actual_width > 0 and actual_height > 0:
                shown_width, shown_height = actual_width, actual_height
        except cv2.error:
            pass
        px = max(
            0, min(round(x * self.preview_width / shown_width), self.preview_width - 1)
        )
        py = max(
            0,
            min(round(y * self.preview_height / shown_height), self.preview_height - 1),
        )
        return (
            max(0, min(round(px / self.scale), self.image_width - 1)),
            max(0, min(round(py / self.scale), self.image_height - 1)),
        )

    def mouse(self, event, x, y, _flags, _userdata) -> None:
        image_point = self._image_point(x, y)
        self.preview_cursor = image_point
        in_crop = (
            self.crop_x1 <= image_point[0] <= self.crop_x2
            and self.crop_y1 <= image_point[1] <= self.crop_y2
        )
        point = (image_point[0] - self.crop_x1, image_point[1] - self.crop_y1)
        if event == cv2.EVENT_LBUTTONDOWN:
            if not in_crop:
                self.drag_start = None
                self.drag_mode = None
                self.notice = "Start the drag inside the orange crop outline."
                return
            self.drag_start = point
            if self.add_mode:
                self.selected = None
                self.drag_mode = "new"
                return
            self.selected = next(
                (
                    index
                    for index in range(len(self.boxes) - 1, -1, -1)
                    if self.boxes[index][1] <= point[0] <= self.boxes[index][3]
                    and self.boxes[index][2] <= point[1] <= self.boxes[index][4]
                ),
                None,
            )
            if self.selected is None:
                self.drag_mode = "new"
            else:
                self.original_box = self.boxes[self.selected].copy()
                _, x1, y1, x2, y2 = self.original_box
                corners = [
                    ((x1, y1), (x2, y2)),
                    ((x2, y1), (x1, y2)),
                    ((x1, y2), (x2, y1)),
                    ((x2, y2), (x1, y1)),
                ]
                corner_radius = max(12, round(12 / self.scale))
                closest = min(
                    corners,
                    key=lambda item: (
                        (item[0][0] - point[0]) ** 2 + (item[0][1] - point[1]) ** 2
                    ),
                )
                if (closest[0][0] - point[0]) ** 2 + (
                    closest[0][1] - point[1]
                ) ** 2 <= corner_radius**2:
                    self.drag_mode = "resize"
                    self.resize_anchor = closest[1]
                else:
                    self.drag_mode = "move"
        elif event == cv2.EVENT_MOUSEMOVE and self.drag_start:
            if (
                self.drag_mode == "move"
                and self.selected is not None
                and self.original_box
            ):
                dx, dy = point[0] - self.drag_start[0], point[1] - self.drag_start[1]
                _, x1, y1, x2, y2 = self.original_box
                box_width, box_height = x2 - x1, y2 - y1
                x1 = max(0, min(self.width - box_width, x1 + dx))
                y1 = max(0, min(self.height - box_height, y1 + dy))
                self.boxes[self.selected] = [
                    self.original_box[0],
                    x1,
                    y1,
                    x1 + box_width,
                    y1 + box_height,
                ]
            elif (
                self.drag_mode == "resize"
                and self.selected is not None
                and self.resize_anchor
            ):
                anchor_x, anchor_y = self.resize_anchor
                x1, x2 = sorted((anchor_x, point[0]))
                y1, y2 = sorted((anchor_y, point[1]))
                self.boxes[self.selected][1:] = [x1, y1, x2, y2]
        elif event == cv2.EVENT_LBUTTONUP and self.drag_start:
            if self.drag_mode == "new":
                point = (
                    max(0, min(self.width, point[0])),
                    max(0, min(self.height, point[1])),
                )
                x1, x2 = sorted((self.drag_start[0], point[0]))
                y1, y2 = sorted((self.drag_start[1], point[1]))
                if x2 - x1 >= 2 and y2 - y1 >= 2:
                    self.boxes.append([self.current_class, x1, y1, x2, y2])
                    self.selected = len(self.boxes) - 1
                    self.notice = (
                        f"Added {self.names[self.current_class]} box. "
                        f"Total boxes: {len(self.boxes)}. Press Enter to save."
                    )
                else:
                    self.notice = "Box was too small; drag farther before releasing."
            self.drag_start = None
            self.drag_mode = None
            self.original_box = None
            self.resize_anchor = None

    def render(self):
        canvas = cv2.resize(
            self.image,
            (self.preview_width, self.preview_height),
            interpolation=cv2.INTER_AREA if self.scale < 1 else cv2.INTER_LINEAR,
        )
        roi_top_left = (
            round(self.crop_x1 * self.scale),
            round(self.crop_y1 * self.scale),
        )
        roi_bottom_right = (
            round(self.crop_x2 * self.scale),
            round(self.crop_y2 * self.scale),
        )
        cv2.rectangle(canvas, roi_top_left, roi_bottom_right, (255, 180, 0), 2)
        for index, (class_id, x1, y1, x2, y2) in enumerate(self.boxes):
            p1 = (
                round((x1 + self.crop_x1) * self.scale),
                round((y1 + self.crop_y1) * self.scale),
            )
            p2 = (
                round((x2 + self.crop_x1) * self.scale),
                round((y2 + self.crop_y1) * self.scale),
            )
            color = (0, 210, 255) if index == self.selected else (50, 220, 50)
            cv2.rectangle(canvas, p1, p2, color, 2)
            cv2.putText(
                canvas,
                f"{class_id}: {self.names[class_id]}",
                (p1[0], max(18, p1[1] - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
        if self.drag_mode == "new" and self.drag_start and self.preview_cursor:
            p1 = (
                round((self.drag_start[0] + self.crop_x1) * self.scale),
                round((self.drag_start[1] + self.crop_y1) * self.scale),
            )
            p2 = tuple(round(value * self.scale) for value in self.preview_cursor)
            cv2.rectangle(canvas, p1, p2, (255, 180, 0), 2)
        help_text = (
            f"{self.image_name} | {'ADD' if self.add_mode else 'EDIT'} mode "
            f"| class {self.current_class}: {self.names[self.current_class]} | "
            "0-9 . -=class, E=mode, Del=delete, W/Enter=save, S=skip, Q=quit"
        )
        cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 30), (25, 25, 25), -1)
        cv2.putText(
            canvas,
            help_text[:180],
            (8, 21),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.rectangle(
            canvas,
            (0, canvas.shape[0] - 26),
            (canvas.shape[1], canvas.shape[0]),
            (25, 25, 25),
            -1,
        )
        cv2.putText(
            canvas,
            self.notice[:150],
            (8, canvas.shape[0] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 240, 180),
            1,
            cv2.LINE_AA,
        )
        return canvas

    def run(self) -> str:
        cv2.namedWindow(self.WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.WINDOW, self.preview_width, self.preview_height)
        cv2.setMouseCallback(self.WINDOW, self.mouse)
        while True:
            cv2.imshow(self.WINDOW, self.render())
            key = cv2.waitKeyEx(20)
            key = key & 0xFF
            if key in (13, 10, ord("w")):
                self.notice = "Accepted: saving crop and labels."
                cv2.imshow(self.WINDOW, self.render())
                cv2.waitKey(1)
                return "save"
            if key in (ord("q"), 27):
                return "quit"
            if key == ord("s"):
                return "skip"
            if key in (8, 127, 255):
                if self.selected is not None:
                    self.boxes.pop(self.selected)
                    self.selected = None
                elif self.boxes:
                    self.boxes.pop()
            elif key in (ord("a"), 81):
                self.current_class = (self.current_class - 1) % len(self.names)
            elif key in (ord("d"), 83):
                self.current_class = (self.current_class + 1) % len(self.names)
            elif ord("0") <= key <= ord("9"):
                self._set_class(2 + key - ord("0"))
            elif key == ord("."):
                self._set_class(1)
            elif key == ord("-"):
                self._set_class(0)
            elif key == ord("e"):
                self.add_mode = not self.add_mode
                self.notice = (
                    "Add mode: drag creates a box, including over existing predictions."
                    if self.add_mode
                    else "Edit mode: drag an existing box to move; drag a corner to resize."
                )

            try:
                if cv2.getWindowProperty(self.WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    return "save"
            except cv2.error:
                return "save"

    def _set_class(self, class_id: int) -> None:
        if class_id not in self.names:
            return
        self.current_class = class_id
        if self.selected is not None:
            self.boxes[self.selected][0] = class_id


def load_backend_env() -> None:
    env_path = BACKEND_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def project_path(value: str, default: Path) -> Path:
    path = Path(value).expanduser() if value else default
    if path.is_absolute():
        return path.resolve()
    for base in (BACKEND_ROOT, REPOSITORY_ROOT, Path.cwd()):
        candidate = (base / path).resolve()
        if candidate.is_file():
            return candidate
    return (BACKEND_ROOT / path).resolve()


def collect_images(inputs: list[Path], recursive: bool) -> list[Path]:
    found: list[Path] = []
    for item in inputs:
        path = item.expanduser().resolve()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            found.append(path)
        elif path.is_dir():
            candidates = path.rglob("*") if recursive else path.iterdir()
            found.extend(
                candidate.resolve()
                for candidate in candidates
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS
            )
        else:
            print(f"Skip missing or unsupported input: {path}", file=sys.stderr)
    return sorted(set(found), key=lambda path: str(path).lower())


def resolve_display_class(model: YOLO) -> int:
    names = model.names
    matches = [
        int(index)
        for index, name in names.items()
        if str(name).strip().lower() == "weight_display"
    ]
    if len(matches) != 1:
        raise ValueError(
            f"crop.pt must have exactly one weight_display class; got {names!r}"
        )
    return matches[0]


def verify_digit_classes(model: YOLO) -> None:
    actual = {int(index): str(name).strip() for index, name in model.names.items()}
    if actual != EXPECTED_CLASSES:
        raise ValueError(
            "best.pt must map classes exactly as 0='-', 1='.', 2='0', ..., 11='9'; "
            f"got {actual!r}"
        )


def detect_display(
    model: YOLO,
    image,
    class_id: int,
    confidence: float,
    image_size: int,
    padding: float,
):
    height, width = image.shape[:2]
    predictions = model.predict(
        source=image,
        conf=confidence,
        imgsz=image_size,
        verbose=False,
        device=torch.device("cpu"),
    )[0]
    if predictions.boxes is None:
        return None
    candidates = []
    for coords, predicted_class, score in zip(
        predictions.boxes.xyxy.tolist(),
        predictions.boxes.cls.tolist(),
        predictions.boxes.conf.tolist(),
        strict=True,
    ):
        if int(predicted_class) != class_id:
            continue
        x1, y1, x2, y2 = map(float, coords)
        pad_x, pad_y = (x2 - x1) * padding, (y2 - y1) * padding
        region = DisplayRegion(
            max(0, round(x1 - pad_x)),
            max(0, round(y1 - pad_y)),
            min(width, round(x2 + pad_x)),
            min(height, round(y2 + pad_y)),
            "red",
            float(score),
        )
        if region.width > 0 and region.height > 0:
            candidates.append((float(score), region))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


def label_text(result, width: int, height: int) -> str:
    if result.boxes is None:
        return ""
    rows = []
    for coords, class_id in zip(
        result.boxes.xyxy.tolist(), result.boxes.cls.tolist(), strict=True,
    ):
        x1, y1, x2, y2 = map(float, coords)
        x1, x2 = max(0.0, min(x1, width)), max(0.0, min(x2, width))
        y1, y2 = max(0.0, min(y1, height)), max(0.0, min(y2, height))
        if x2 <= x1 or y2 <= y1:
            continue
        rows.append(
            f"{int(class_id)} {((x1 + x2) / 2 / width):.6f} "
            f"{((y1 + y2) / 2 / height):.6f} "
            f"{((x2 - x1) / width):.6f} {((y2 - y1) / height):.6f}"
        )
    return "\n".join(rows) + ("\n" if rows else "")


def main() -> int:
    load_backend_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "images", nargs="+", type=Path, help="Input image(s) or folder(s)"
    )
    parser.add_argument(
        "--recursive", action="store_true", help="Scan input folders recursively"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing crops and labels"
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
        "--crop-padding",
        type=float,
        default=float(os.environ.get("ROLL_SCALE_CROP_DIGIT_PADDING", "0.12")),
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
    args = parser.parse_args()

    sources = collect_images(args.images, args.recursive)
    if not sources:
        parser.error("no supported images found")
    if not 0 < args.crop_confidence <= 1 or not 0 < args.digit_confidence <= 1:
        parser.error("confidence values must be greater than 0 and at most 1")
    if args.crop_image_size < 32 or args.digit_image_size < 32 or args.crop_padding < 0:
        parser.error("image sizes must be >= 32 and crop padding must be non-negative")

    crop_path = project_path(
        os.environ.get("ROLL_SCALE_CROP_DIGIT_MODEL", ""),
        BACKEND_ROOT / "model" / "crop.pt",
    )
    digit_path = project_path(
        os.environ.get("ROLL_SCALE_DIGIT_MODEL", ""), BACKEND_ROOT / "model" / "best.pt"
    )
    for model_path in (crop_path, digit_path):
        if not model_path.is_file():
            parser.error(f"model file not found: {model_path}")

    cv2.setNumThreads(1)
    torch.set_num_threads(max(1, min(2, (os.cpu_count() or 2) // 2)))
    crop_model, digit_model = YOLO(str(crop_path)), YOLO(str(digit_path))
    crop_class = resolve_display_class(crop_model)
    verify_digit_classes(digit_model)
    IMAGE_OUTPUT.mkdir(parents=True, exist_ok=True)
    LABEL_OUTPUT.mkdir(parents=True, exist_ok=True)

    # If basenames collide across input folders, add the source folder to keep
    # crop/label pairs distinct.
    basename_counts: dict[str, int] = {}
    for source in sources:
        basename_counts[source.name.lower()] = (
            basename_counts.get(source.name.lower(), 0) + 1
        )

    saved = missed = skipped = 0
    for source in sources:
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            print(f"Could not decode image: {source}", file=sys.stderr)
            missed += 1
            continue
        output_name = source.name
        if basename_counts[source.name.lower()] > 1:
            output_name = f"{source.parent.name}_{source.name}"
        image_target = IMAGE_OUTPUT / output_name
        label_target = LABEL_OUTPUT / f"{Path(output_name).stem}.txt"
        if not args.overwrite and (image_target.exists() or label_target.exists()):
            print(
                f"Already exists; skipped: {output_name} (use --overwrite to replace)"
            )
            skipped += 1
            continue

        region = detect_display(
            crop_model,
            image,
            crop_class,
            args.crop_confidence,
            args.crop_image_size,
            args.crop_padding,
        )
        if region is None:
            print(f"No display detected: {source.name}")
            missed += 1
            continue
        crop = image[region.y1 : region.y2, region.x1 : region.x2]
        if crop.size == 0:
            print(f"Empty display crop: {source.name}", file=sys.stderr)
            missed += 1
            continue
        prediction = digit_model.predict(
            source=crop,
            conf=args.digit_confidence,
            imgsz=args.digit_image_size,
            verbose=False,
            device=torch.device("cpu"),
        )[0]
        height, width = crop.shape[:2]
        if not cv2.imwrite(str(image_target), crop):
            print(f"Could not save crop: {image_target}", file=sys.stderr)
            missed += 1
            continue
        try:
            label_target.write_text(
                label_text(prediction, width, height), encoding="utf-8"
            )
        except OSError as exc:
            print(f"Could not save labels to {label_target}: {exc}", file=sys.stderr)
            missed += 1
            continue
        if not image_target.is_file() or not label_target.is_file():
            print(f"Save verification failed for {output_name}", file=sys.stderr)
            missed += 1
            continue
        count = 0 if prediction.boxes is None else len(prediction.boxes)
        print(
            f"{source.name}: saved display crop + {count} labels\n"
            f"  image: {image_target.resolve()}\n"
            f"  label: {label_target.resolve()}"
        )
        saved += 1

    print(f"Done: {saved} saved, {missed} missed, {skipped} skipped.")
    print(f"Images: {IMAGE_OUTPUT}\nLabels: {LABEL_OUTPUT}")
    return 0 if saved or not missed else 1


if __name__ == "__main__":
    raise SystemExit(main())
