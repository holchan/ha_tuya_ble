"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass, field

import logging

from homeassistant.components.select import (
    SelectEntityDescription,
    SelectEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    FINGERBOT_MODE_PROGRAM,
    FINGERBOT_MODE_PUSH,
    FINGERBOT_MODE_SWITCH,
)
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import TuyaBLEDataPointType, TuyaBLEDevice

_LOGGER = logging.getLogger(__name__)


@dataclass
class TuyaBLESelectMapping:
    dp_id: int
    description: SelectEntityDescription
    force_add: bool = True
    dp_type: TuyaBLEDataPointType | None = None


@dataclass
class TemperatureUnitDescription(SelectEntityDescription):
    key: str = "temperature_unit"
    icon: str = "mdi:thermometer"
    entity_category: EntityCategory = EntityCategory.CONFIG


@dataclass
class TuyaBLEFingerbotModeMapping(TuyaBLESelectMapping):
    description: SelectEntityDescription = field(
        default_factory=lambda: SelectEntityDescription(
            key="fingerbot_mode",
            entity_category=EntityCategory.CONFIG,
            options=
                [
                    FINGERBOT_MODE_PUSH, 
                    FINGERBOT_MODE_SWITCH,
                    FINGERBOT_MODE_PROGRAM,
                ],
        )
    )


@dataclass
class TuyaBLECategorySelectMapping:
    products: dict[str, list[TuyaBLESelectMapping]] | None = None
    mapping: list[TuyaBLESelectMapping] | None = None


mapping: dict[str, TuyaBLECategorySelectMapping] = {
    "co2bj": TuyaBLECategorySelectMapping(
        products={
            "59s19z5m":  # CO2 Detector
            [
                TuyaBLESelectMapping(
                    dp_id=101,
                    description=TemperatureUnitDescription(
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                    )
                ),
            ],
        },
    ),
    "ms": TuyaBLECategorySelectMapping(
        products={
            **dict.fromkeys(
                ["ludzroix", "isk2p555"], # Smart Lock
                [
                    TuyaBLESelectMapping(
                        dp_id=31,
                        description=SelectEntityDescription(
                            key="beep_volume",
                            options=[
                                "mute",
                                "low",
                                "normal",
                                "high",
                            ],
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                ]
            ),
        }
    ),
    "jtmspro": TuyaBLECategorySelectMapping(
        products={
            "xicdxood":  # Raycube K7 Pro+
            [
                TuyaBLESelectMapping(
                    dp_id=31,
                    description=SelectEntityDescription(
                        key="beep_volume",
                        options=[
                            "Mute",
                            "Low",
                            "Normal",
                            "High",
                        ],
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
                TuyaBLESelectMapping(
                    dp_id=28,
                    description=SelectEntityDescription(
                        key="language",
                        options=[
                            "Chinese Simplified",
                            "English",
                            "Arabic",
                            "Indonesian",
                            "Portuguese",
                        ],
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
            ],
        }
    ),
    "szjqr": TuyaBLECategorySelectMapping(
        products={
            **dict.fromkeys(
                ["3yqdo5yt", "xhf790if"],  # CubeTouch 1s and II
                [
                    TuyaBLEFingerbotModeMapping(dp_id=2),
                ],
            ),
            **dict.fromkeys(
                [
                    "blliqpsj",
                    "ndvkgsrm",
                    "yiihr7zh",
                    "riecov42",
                    "neq16kgd"
                ],  # Fingerbot Plus
                [
                    TuyaBLEFingerbotModeMapping(dp_id=8),
                ],
            ),
            **dict.fromkeys(
                ["ltak7e1p", "y6kttvd6", "yrnk7mnn",
                    "nvr2rocq", "bnt7wajf", "rvdceqjh",
                    "5xhbk964"],  # Fingerbot
                [
                    TuyaBLEFingerbotModeMapping(dp_id=8),
                ],
            ),
        },
    ),
    "kg": TuyaBLECategorySelectMapping(
        products={
            **dict.fromkeys(
                [
                    "mknd4lci",
                    "riecov42"
                ],  # Fingerbot Plus
                [
                    TuyaBLEFingerbotModeMapping(dp_id=101),
                ],
            ),
        },
    ),
    "wsdcg": TuyaBLECategorySelectMapping(
        products={
            "ojzlzzsw":  # Soil moisture sensor
            [
                TuyaBLESelectMapping(
                    dp_id=9,
                    description=TemperatureUnitDescription(
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                        entity_registry_enabled_default=False,
                    )
                ),
            ],
        },
    ),
    "znhsb": TuyaBLECategorySelectMapping(
        products={
            "cdlandip":  # Smart water bottle
            [
                TuyaBLESelectMapping(
                    dp_id=106,
                    description=TemperatureUnitDescription(
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                    )
                ),
                TuyaBLESelectMapping(
                    dp_id=107,
                    description=SelectEntityDescription(
                        key="reminder_mode",
                        options=[
                            "interval_reminder",
                            "schedule_reminder",
                        ],
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
            ],
        },
    ),
    "znhsb": TuyaBLECategorySelectMapping(
        products={
            "cdlandip":  # Smart water bottle
            [
                TuyaBLESelectMapping(
                    dp_id=106,
                    description=TemperatureUnitDescription(
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                    )
                ),
                TuyaBLESelectMapping(
                    dp_id=107,
                    description=SelectEntityDescription(
                        key="reminder_mode",
                        options=[
                            "interval_reminder",
                            "alarm_reminder",
                        ],
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
            ],
        },
    ),
    "sfkzq": TuyaBLECategorySelectMapping(
        products={
            "0axr5s0b":  # Valve Controller
            [
                TuyaBLESelectMapping(
                    dp_id=10,
                    description=SelectEntityDescription(
                        key="weather_delay",
                        options=[
                            "cancel",
                            "24h",
                            "48h",
                            "72h",
                        ],
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
                TuyaBLESelectMapping(
                    dp_id=12,
                    description=SelectEntityDescription(
                        key="work_state",
                        options=[
                            "auto",
                            "manual",
                            "idle"
                        ],
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
            ],
        }
    ),
}


def get_mapping_by_device(
    device: TuyaBLEDevice
) -> list[TuyaBLECategorySelectMapping]:
    category = mapping.get(device.category)
    if category is not None and category.products is not None:
        product_mapping = category.products.get(device.product_id)
        if product_mapping is not None:
            return product_mapping
        if category.mapping is not None:
            return category.mapping
        else:
            return []
    else:
        return []


class TuyaBLESelect(TuyaBLEEntity, SelectEntity):
    """Representation of a Tuya BLE select."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLESelectMapping,
    ) -> None:
        _LOGGER.debug(
            "Initializing TuyaBLESelect with device: %s, product: %s, mapping: %s",
            device, product, mapping
        )
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping
        _LOGGER.debug("TuyaBLESelect initialized with mapping: %s", self._mapping)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        _LOGGER.debug("Getting current option for device: %s", self._device)
        datapoint = self._device.datapoints[self._mapping.dp_id]
        if datapoint:
            current_option = datapoint.value
            _LOGGER.debug("Current option obtained from datapoint: %s", current_option)
            return current_option
        _LOGGER.debug("No datapoint found, returning None")
        return None

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("Selecting option for device: %s to %s", self._device, option)
        datapoint = self._device.datapoints.get_or_create(
            self._mapping.dp_id,
            TuyaBLEDataPointType.DT_ENUM,
            option,
        )
        if datapoint:
            _LOGGER.debug("Setting datapoint value to: %s", option)
            self._hass.create_task(datapoint.set_value(option))

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        result = super().available
        _LOGGER.debug("Checking availability for device: %s, result: %s", self._device, result)
        return result


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE selects."""
    _LOGGER.debug("Setting up Tuya BLE selects for entry: %s", entry.entry_id)
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    mappings = get_mapping_by_device(data.device)
    _LOGGER.debug("Mappings obtained for device: %s", mappings)
    entities: list[TuyaBLESelect] = []
    for mapping in mappings:
        if mapping.force_add or data.device.datapoints.has_id(
            mapping.dp_id, mapping.dp_type
        ):
            _LOGGER.debug("Adding TuyaBLESelect entity for mapping: %s", mapping)
            entities.append(
                TuyaBLESelect(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    mapping,
                )
            )
    async_add_entities(entities)
    _LOGGER.debug("Entities added: %s", entities)
