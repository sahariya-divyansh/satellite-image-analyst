"""Tests for water change detection logic."""

import numpy as np
import pytest

from satellite_analyst.analysis.change import WaterChangeClass, detect_water_change


def test_detect_water_change_classes() -> None:
    # 2x2 grid representing all transitions
    # (0, 0): Dry in A, Dry in B -> DRY (0)
    # (0, 1): Dry in A, Water in B -> GAINED (1)
    # (1, 0): Water in A, Dry in B -> LOST (2)
    # (1, 1): Water in A, Water in B -> PERSISTENT (3)

    mask_a = np.array([[False, False], [True, True]], dtype=bool)
    mask_b = np.array([[False, True], [False, True]], dtype=bool)

    change = detect_water_change(mask_a, mask_b)

    assert change[0, 0] == WaterChangeClass.DRY
    assert change[0, 1] == WaterChangeClass.GAINED
    assert change[1, 0] == WaterChangeClass.LOST
    assert change[1, 1] == WaterChangeClass.PERSISTENT


def test_detect_water_change_shape_mismatch() -> None:
    mask_a = np.zeros((10, 10), dtype=bool)
    mask_b = np.zeros((12, 12), dtype=bool)

    with pytest.raises(ValueError, match="Shape mismatch"):
        detect_water_change(mask_a, mask_b)
