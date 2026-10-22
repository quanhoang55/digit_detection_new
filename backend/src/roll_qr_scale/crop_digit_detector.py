"""Use the crop.pt detector to locate the display before digit recognition."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from collections.abc import Sequence

import numpy as np
import torch
from ultralytics import YOLO

from backend.cv.digit_detector import (
    DetectionRun,
    DigitDetector,
    _reading_score,
    top_display_rows,
)
from backend.cv.display_locator import DisplayRegion, locate_display_candidates, scaled_region

logger = logging.getLogger(__name__)


class CropModelDigitDetector(DigitDetector):
    """Digit detector whose full-frame ROI comes from the trained crop model."""

    roi_method = "crop.pt-weight-display"

    def __init__(
        self,
        digit_model_path: Path,
        crop_model_path: Path,
        confidence: float,
        *,
        crop_confidence: float = 0.001,
        crop_image_size: int = 640,
        crop_padding: float = 0.12,
        display_colors: Sequence[str] = ("red",),
        max_candidates: int = 5,
        image_size: int = 736,
        prefer_top_row: bool = True,
        cpu_threads: int | None = None,
    ) -> None:
        super().__init__(
            digit_model_path,
            confidence,
            display_colors=display_colors,
            max_candidates=max_candidates,
            image_size=image_size,
            prefer_top_row=prefer_top_row,
            cpu_threads=cpu_threads,
        )
        if not 0 < crop_confidence <= 1:
            raise ValueError("crop_confidence must be greater than 0 and at most 1")
        if crop_image_size < 32:
            raise ValueError("crop_image_size must be at least 32")
        if crop_padding < 0:
            raise ValueError("crop_padding must be non-negative")

        self.crop_model_path = Path(crop_model_path)
        self.crop_confidence = float(crop_confidence)
        self.crop_image_size = int(crop_image_size)
        self.crop_padding = float(crop_padding)
        self.crop_model = YOLO(str(self.crop_model_path))
        self.crop_class_id = self._resolve_crop_class(self.crop_model.names)
        logger.info(
            "Loaded display crop model %s (class=%s, confidence=%.4f, padding=%.3f)",
            self.crop_model_path,
            self.crop_model.names[self.crop_class_id],
            self.crop_confidence,
            self.crop_padding,
        )

    @staticmethod
    def _resolve_crop_class(names: dict[int, str]) -> int:
        matches = [
            int(index)
            for index, name in names.items()
            if str(name).strip().lower() == "weight_display"
        ]
        if len(matches) != 1:
            raise ValueError(
                "crop model must contain exactly one 'weight_display' class; "
                f"got {names!r}"
            )
        return matches[0]

    def _display_candidates(
        self, image: np.ndarray
    ) -> list[tuple[DisplayRegion, float]]:
        options: dict[str, object] = {
            "conf": self.crop_confidence,
            "imgsz": self.crop_image_size,
            "verbose": False,
        }
        if self.cpu_threads is not None:
            torch.set_num_threads(self.cpu_threads)
            options["device"] = torch.device("cpu")
        result = self.crop_model.predict(source=image, **options)[0]
        if result.boxes is None:
            return []

        height, width = image.shape[:2]
        regions: list[tuple[DisplayRegion, float]] = []
        for coordinates, class_id, score in zip(
            result.boxes.xyxy.tolist(),
            result.boxes.cls.tolist(),
            result.boxes.conf.tolist(),
            strict=True,
        ):
            if int(class_id) != self.crop_class_id:
                continue
            x1, y1, x2, y2 = (float(value) for value in coordinates)
            if x2 <= x1 or y2 <= y1:
                continue
            padding_x = (x2 - x1) * self.crop_padding
            padding_y = (y2 - y1) * self.crop_padding
            region = DisplayRegion(
                max(0, round(x1 - padding_x)),
                max(0, round(y1 - padding_y)),
                min(width, round(x2 + padding_x)),
                min(height, round(y2 + padding_y)),
                "red",
                float(score),
            )
            if region.width >= 20 and region.height >= 10:
                regions.append((region, float(score)))

        if self.prefer_top_row:
            # Gross is the top aligned scale row. Never select a readable
            # tare/net row merely because its zeros have higher confidence.
            top_rows = top_display_rows([region for region, _ in regions])
            regions = [(region, score) for region, score in regions if region in top_rows]
        regions.sort(key=lambda item: item[1], reverse=True)
        return regions[: self.max_candidates]

    def detect_with_details(self, image: np.ndarray) -> DetectionRun:
        started = time.perf_counter()
        if image is None or not isinstance(image, np.ndarray) or image.ndim != 3:
            raise ValueError("image must be a BGR color image")

        candidates = self._display_candidates(image)
        if not candidates:
            return DetectionRun(
                [], None, 0, None, None, 0, 1,
                (time.perf_counter() - started) * 1000,
                self.model_version,
            )

        # Anchor to the strongest trained Gross box. A tall secondary box
        # spanning two rows must not reintroduce tare/net as an alternative.
        anchor, anchor_confidence = candidates[0]
        candidates = [(anchor, anchor_confidence, "original")]
        contexts = top_display_rows(locate_display_candidates(
            image, colors=self.display_colors, max_candidates=self.max_candidates))
        for context in contexts:
            region = scaled_region(context, 0.7, image.shape)
            overlap = max(0, min(region.x2, anchor.x2) - max(region.x1, anchor.x1)) * max(
                0, min(region.y2, anchor.y2) - max(region.y1, anchor.y1))
            union = region.width * region.height + anchor.width * anchor.height - overlap
            # Recover context cut tightly by crop.pt, only on the same row.
            # The digit checkpoint remains the colleague's second model.
            if union and overlap / union >= 0.5 and region != anchor:
                candidates.append((region, anchor_confidence, "original"))
                candidates.append((region, anchor_confidence, "sharpened"))
                break

        best: tuple[float, DisplayRegion, float, list, str] | None = None
        confident_readings: set[str] = set()
        ignored_none_total = 0
        for region, crop_confidence, preprocessing in candidates:
            proposals, ignored_none = self._predict_crop(image, region, preprocessing)
            ignored_none_total += ignored_none
            # A weak digit must reject the whole reading. Removing it here
            # could turn 6308 into 6.30 before the service checks confidence.
            accepted = proposals
            raw = "".join(str(item.value) for item in accepted)
            if raw.isdecimal() and 3 <= len(raw) <= 6 and min(
                (item.confidence for item in accepted), default=0) >= self.confidence:
                confident_readings.add(raw)
            score = _reading_score(region, accepted) + crop_confidence * 0.1
            if best is None or score > best[0]:
                best = score, region, crop_confidence, accepted, preprocessing

        assert best is not None
        _, region, crop_confidence, digits, preprocessing = best
        if len(confident_readings) > 1:
            # Conflicting complete rows require an operator decision.
            digits = []
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.debug(
            "crop.pt display=%s confidence=%.4f digits=%s elapsed_ms=%.1f",
            region.bbox,
            crop_confidence,
            [(item.value, round(item.confidence, 3)) for item in digits],
            elapsed_ms,
        )
        return DetectionRun(
            digits,
            region,
            len(candidates),
            1.0,
            f"crop.pt+{preprocessing}",
            ignored_none_total,
            1 + len(candidates),
            elapsed_ms,
            self.model_version,
        )

    def detect_live(
        self, image: np.ndarray, previous: DetectionRun | None = None
    ) -> DetectionRun:
        # The crop model tracks the display afresh in each frame, so movement
        # and changing digit widths do not depend on a stale ROI.
        del previous
        return self.detect_with_details(image)
