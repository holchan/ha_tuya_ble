"""Utility methods for the Tuya integration."""
from __future__ import annotations
import logging

_LOGGER = logging.getLogger(__name__)

def remap_value(
    value: float | int,
    from_min: float | int = 0,
    from_max: float | int = 255,
    to_min: float | int = 0,
    to_max: float | int = 255,
    reverse: bool = False,
) -> float:
    """Remap a value from its current range, to a new range."""
    _LOGGER.debug(
        "Remapping value: %s from range (%s, %s) to range (%s, %s), reverse: %s",
        value, from_min, from_max, to_min, to_max, reverse
    )
    if reverse:
        value = from_max - value + from_min
        _LOGGER.debug("Value reversed to: %s", value)
    remapped_value = ((value - from_min) / (from_max - from_min)) * (to_max - to_min) + to_min
    _LOGGER.debug("Remapped value: %s", remapped_value)
    return remapped_value
