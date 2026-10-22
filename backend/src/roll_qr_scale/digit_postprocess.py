"""Backend-side checks for digits that are unsupported by the LED pixels."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

import numpy as np


def resolve_weak_crop_disagreement(frame: np.ndarray, run: object, detector: object) -> None:
    """Use two alternate crops to break a low-confidence digit-row tie."""

    if getattr(detector, "roi_method", "") == "crop.pt-weight-display":
        return

    display = getattr(run, "display", None)
    digits = getattr(run, "digits", None)
    if (
        not display
        or not digits
        or min(float(item.confidence) for item in digits) >= 0.45
    ):
        return
    if "red" not in {
        str(color).strip().lower()
        for color in getattr(detector, "display_colors", ("red",))
    }:
        return

    previous_scale = float(getattr(run, "crop_scale", 1.0) or 1.0)
    if previous_scale <= 0:
        return
    height, width = frame.shape[:2]
    center_x = (display.x1 + display.x2) / 2
    center_y = (display.y1 + display.y2) / 2
    base_width = display.width / previous_scale
    base_height = display.height / previous_scale

    def crop_region(scale: float) -> object:
        half_width = base_width * scale / 2
        half_height = base_height * scale / 2
        x1 = max(0, round(center_x - half_width))
        y1 = max(0, round(center_y - half_height))
        x2 = min(width, round(center_x + half_width))
        y2 = min(height, round(center_y + half_height))
        return type(display)(x1, y1, x2, y2, display.color, display.locator_score)

    baseline = sorted(digits, key=lambda item: item.box.x + item.box.width / 2)
    readings = [baseline]
    predict = getattr(detector, "_predict_crop", None)
    if not callable(predict):
        return
    for scale in (0.7, 1.0):
        proposals, _ = predict(frame, crop_region(scale), "original")
        accepted = [
            item
            for item in proposals
            if float(item.confidence) >= float(getattr(detector, "confidence", 0.0))
        ]
        if 3 <= len(accepted) <= 6:
            readings.append(
                sorted(accepted, key=lambda item: item.box.x + item.box.width / 2)
            )

    signatures = ["".join(str(item.value) for item in row) for row in readings]
    winner, votes = Counter(signatures).most_common(1)[0]
    if winner != signatures[0] and votes > len(readings) / 2:
        run.digits[:] = readings[signatures.index(winner)]


def remove_unlit_trailing_digit(
    frame: np.ndarray,
    digits: Sequence[object],
    *,
    display_colors: Iterable[str],
) -> list[object]:
    """Preserve every detected digit; confidence decides whether to reject.

    LED color and box width cannot prove that a weak trailing digit is noise.
    Dropping it changes both the integer and decimal places (6308 -> 6.30).
    Retain the weak digit so the caller rejects the entire uncertain reading.
    """

    return sorted(digits, key=lambda item: item.box.x + item.box.width / 2)
