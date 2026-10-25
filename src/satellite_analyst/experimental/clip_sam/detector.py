"""Experimental open-vocabulary object detector (e.g., brick kilns, aquaculture).

CAVEAT: This module is strictly experimental, operates behind feature flags,
and outputs uncalibrated heuristic confidences. It is isolated from the core
defensible water analysis pipeline.
"""

from typing import Any

import numpy as np


class ExperimentalObjectDetector:
    """Zero-shot object detector using CLIP and Segment Anything (SAM)."""

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        self.confidence_threshold = confidence_threshold

    def detect_objects(
        self,
        _rgb_image: np.ndarray,
        _prompt: str,
    ) -> list[dict[str, Any]]:
        """Identify candidate objects matching text prompt."""
        # Uncalibrated experimental stub
        return []
