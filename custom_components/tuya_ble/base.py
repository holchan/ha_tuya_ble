"""Tuya Home Assistant Base Device Model."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import struct
from typing import Any, Literal, Self, overload
import logging

from tuya_iot import TuyaDevice, TuyaDeviceManager

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import (
    DPCode,
)

from .util import remap_value

_LOGGER = logging.getLogger(__name__)


@dataclass
class IntegerTypeData:
    """Integer Type Data."""

    dpcode: DPCode
    min: int
    max: int
    scale: float
    step: float
    unit: str | None = None
    type: str | None = None

    def __post_init__(self):
        _LOGGER.debug(
            "Initialized IntegerTypeData with dpcode: %s, min: %d, max: %d, scale: %f, step: %f, unit: %s, type: %s",
            self.dpcode, self.min, self.max, self.scale, self.step, self.unit, self.type
        )

    @property
    def max_scaled(self) -> float:
        """Return the max scaled."""
        max_scaled_value = self.scale_value(self.max)
        _LOGGER.debug("Max scaled value: %f", max_scaled_value)
        return max_scaled_value

    @property
    def min_scaled(self) -> float:
        """Return the min scaled."""
        min_scaled_value = self.scale_value(self.min)
        _LOGGER.debug("Min scaled value: %f", min_scaled_value)
        return min_scaled_value

    @property
    def step_scaled(self) -> float:
        """Return the step scaled."""
        step_scaled_value = self.step / (10**self.scale)
        _LOGGER.debug("Step scaled value: %f", step_scaled_value)
        return step_scaled_value

    def scale_value(self, value: float | int) -> float:
        """Scale a value."""
        scaled_value = value / (10**self.scale)
        _LOGGER.debug("Scaled value: %f from original value: %s", scaled_value, value)
        return scaled_value

    def scale_value_back(self, value: float | int) -> int:
        """Return raw value for scaled."""
        raw_value = int(value * (10**self.scale))
        _LOGGER.debug("Raw value: %d from scaled value: %s", raw_value, value)
        return raw_value

    def remap_value_to(
        self,
        value: float,
        to_min: float | int = 0,
        to_max: float | int = 255,
        reverse: bool = False,
    ) -> float:
        """Remap a value from this range to a new range."""
        remapped_value = remap_value(value, self.min, self.max, to_min, to_max, reverse)
        _LOGGER.debug(
            "Remapped value: %f from original value: %f with range (%d, %d) to range (%d, %d), reverse: %s",
            remapped_value, value, self.min, self.max, to_min, to_max, reverse
        )
        return remapped_value

    def remap_value_from(
        self,
        value: float,
        from_min: float | int = 0,
        from_max: float | int = 255,
        reverse: bool = False,
    ) -> float:
        """Remap a value from its current range to this range."""
        remapped_value = remap_value(value, from_min, from_max, self.min, self.max, reverse)
        _LOGGER.debug(
            "Remapped value: %f from original value: %f with range (%d, %d) to range (%d, %d), reverse: %s",
            remapped_value, value, from_min, from_max, self.min, self.max, reverse
        )
        return remapped_value

    @classmethod
    def from_json(cls, dpcode: DPCode, data: str | dict) -> IntegerTypeData | None:
        """Load JSON string and return a IntegerTypeData object."""
        _LOGGER.debug("Loading IntegerTypeData from JSON: %s", data)
        if isinstance(data, str):
            parsed = json.loads(data)
        else:
            parsed = data

        if parsed is None:
            _LOGGER.warning("Parsed data is None")
            return None

        instance = cls(
            dpcode,
            min=int(parsed["min"]),
            max=int(parsed["max"]),
            scale=float(parsed["scale"]),
            step=max(float(parsed["step"]), 1),
            unit=parsed.get("unit"),
            type=parsed.get("type"),
        )
        _LOGGER.debug("Created IntegerTypeData from JSON: %s", instance)
        return instance

    @classmethod
    def from_dict(cls, dpcode: DPCode, data: dict | None) -> IntegerTypeData | None:
        """Load Dict and return a IntegerTypeData object."""
        _LOGGER.debug("Loading IntegerTypeData from dict: %s", data)
        if not data:
            _LOGGER.warning("Data is None or empty")
            return None

        instance = cls(
            dpcode,
            min=int(data.get("min", 0)),
            max=int(data.get("max", 0)),
            scale=float(data.get("scale", 0)),
            step=max(float(data.get("step", 0)), 1),
            unit=data.get("unit"),
            type=data.get("type"),
        )
        _LOGGER.debug("Created IntegerTypeData from dict: %s", instance)
        return instance

@dataclass
class EnumTypeData:
    """Enum Type Data."""

    dpcode: DPCode
    range: list[str]

    def __post_init__(self):
        _LOGGER.debug(
            "Initialized EnumTypeData with dpcode: %s, range: %s",
            self.dpcode, self.range
        )

    @classmethod
    def from_json(cls, dpcode: DPCode, data: str) -> EnumTypeData | None:
        """Load JSON string and return a EnumTypeData object."""
        _LOGGER.debug("Loading EnumTypeData from JSON: %s", data)
        if not (parsed := json.loads(data)):
            _LOGGER.warning("Parsed data is None or empty")
            return None
        instance = cls(dpcode, **parsed)
        _LOGGER.debug("Created EnumTypeData from JSON: %s", instance)
        return instance

