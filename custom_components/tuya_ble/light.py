"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass, field

import logging
import json
import copy
import asyncio

from typing import Any, Callable, cast
from enum import IntEnum, StrEnum, Enum

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    DPCode,
    DPType,
    WorkMode,
)

from .base import IntegerTypeData
from .util import remap_value
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import (
    TuyaBLEDevice, 
    TuyaBLEEntityDescription,
)

from homeassistant.exceptions import HomeAssistantError
from bleak_retry_connector import BleakOutOfConnectionSlotsError, establish_connection
import async_timeout
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)

# Most of the code here is identical to the one from the Tuya cloud Light component
@dataclass
class ColorTypeData:
    """Color Type Data."""

    h_type: IntegerTypeData
    s_type: IntegerTypeData
    v_type: IntegerTypeData


DEFAULT_COLOR_TYPE_DATA = ColorTypeData(
    h_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=360, step=1),
    s_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=255, step=1),
    v_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=255, step=1),
)

DEFAULT_COLOR_TYPE_DATA_V2 = ColorTypeData(
    h_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=360, step=1),
    s_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=1000, step=1),
    v_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=1000, step=1),
)


@dataclass
class ColorData:
    """Color Data."""

    type_data: ColorTypeData
    h_value: int
    s_value: int
    v_value: int

    @property
    def hs_color(self) -> tuple[float, float]:
        """Get the HS value from this color data."""
        return (
            self.type_data.h_type.remap_value_to(self.h_value, 0, 360),
            self.type_data.s_type.remap_value_to(self.s_value, 0, 100),
        )

    @property
    def brightness(self) -> int:
        """Get the brightness value from this color data."""
        return round(self.type_data.v_type.remap_value_to(self.v_value, 0, 255))

@dataclass
class TuyaLightEntityDescription(
            TuyaBLEEntityDescription, 
            LightEntityDescription
            ):
    """Describe an Tuya light entity."""

    brightness_max: DPCode | None = None
    brightness_min: DPCode | None = None
    brightness: DPCode | tuple[DPCode, ...] | None = None
    color_data: DPCode | tuple[DPCode, ...] | None = None
    color_mode: DPCode | None = None
    color_temp: DPCode | tuple[DPCode, ...] | None = None
    default_color_type: ColorTypeData = field(
        default_factory=lambda: DEFAULT_COLOR_TYPE_DATA
    ) 


# You can add here description for device for which automatic capabilities setting
# from the cloud data doesn't work - if "key" is "", then products descriptions
# defined fields override the category ones.
# Else the products descriptions are full descriptions and replace the category ones
#
# function/status range are array of dicts descriptions the DPs
# Values are added (replace for same DP) to what we get from the cloud
# ex: 
# key = ""
# functions = [
#   {"code": "switch_led", "dp_id": 1, "type": "Boolean", "values": {}},
#   {"code": "bright_value", "dp_id": 3, "type": "Integer", "values": {"min":10,"max":1000,"scale":0,"step":1}}, 
#   {"code": "colour_data", "dp_id": 5, "type": "Json", "values": {"h":{"min":0,"scale":0,"unit":"","max":360,"step":1},"s":{"min":0,"scale":0,"unit":"","max":1000,"step":1},"v":{"min":0,"scale":0,"unit":"","max":1000,"step":1}}}, 
# ]
# ex:
# <category> : { <productid> : [ TuyaLightEntityDescription(); ... ] },
# ...}
ProductsMapping: dict[str, dict[str, tuple[TuyaLightEntityDescription, ...]]] = {
    "dd": {
        "nvfrtxlq" : (
            TuyaLightEntityDescription(
                key= "", # just override the category description from these set keys 
                values_overrides={
                    # So we still get the right enum values if the product isn't set to DP mode in the cloud settings
                    DPCode.WORK_MODE : {
                        "range" : {
                            WorkMode.COLOUR,
                            "dynamic_mod",
                            "scene_mod",
                            WorkMode.MUSIC,
                        }
                    }
                }
            ),
        )
    }
}

# Copied from standard Tuya light component - we could add some default values here too
LIGHTS: dict[str, tuple[TuyaLightEntityDescription, ...]] = {
    # Curtain Switch
    # https://developer.tuya.com/en/docs/iot/category-clkg?id=Kaiuz0gitil39
    "clkg": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_BACKLIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # String Lights
    # https://developer.tuya.com/en/docs/iot/dc?id=Kaof7taxmvadu
    "dc": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Strip Lights
    # https://developer.tuya.com/en/docs/iot/dd?id=Kaof804aibg2l
    "dd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
            default_color_type=DEFAULT_COLOR_TYPE_DATA_V2,
        ),
    ),
    # Light
    # https://developer.tuya.com/en/docs/iot/categorydj?id=Kaiuyzy3eheyy
    "dj": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=(DPCode.BRIGHT_VALUE_V2, DPCode.BRIGHT_VALUE),
            color_temp=(DPCode.TEMP_VALUE_V2, DPCode.TEMP_VALUE),
            color_data=(DPCode.COLOUR_DATA_V2, DPCode.COLOUR_DATA),
        ),
        # Not documented
        # Based on multiple reports: manufacturer customized Dimmer 2 switches
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_1,
            translation_key="light",
            brightness=DPCode.BRIGHT_VALUE_1,
        ),
    ),
    # Ceiling Fan Light
    # https://developer.tuya.com/en/docs/iot/fsd?id=Kaof8eiei4c2v
    "fsd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
        # Some ceiling fan lights use LIGHT for DPCode instead of SWITCH_LED
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            name=None,
        ),
    ),
    # Ambient Light
    # https://developer.tuya.com/en/docs/iot/ambient-light?id=Kaiuz06amhe6g
    "fwd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Motion Sensor Light
    # https://developer.tuya.com/en/docs/iot/gyd?id=Kaof8a8hycfmy
    "gyd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Humidifier Light
    # https://developer.tuya.com/en/docs/iot/categoryjsq?id=Kaiuz1smr440b
    "jsq": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_data=DPCode.COLOUR_DATA_HSV,
        ),
    ),
    # Switch
    # https://developer.tuya.com/en/docs/iot/s?id=K9gf7o5prgf7s
    "kg": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_BACKLIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Air Purifier
    # https://developer.tuya.com/en/docs/iot/f?id=K9gf46h2s6dzm
    "kj": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Air conditioner
    # https://developer.tuya.com/en/docs/iot/categorykt?id=Kaiuz0z71ov2n
    "kt": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Unknown light product
    # Found as VECINO RGBW as provided by diagnostics
    # Not documented
    "mbd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Unknown product with light capabilities
    # Fond in some diffusers, plugs and PIR flood lights
    # Not documented
    "qjdcz": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Heater
    # https://developer.tuya.com/en/docs/iot/categoryqn?id=Kaiuz18kih0sm
    "qn": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Smart Camera
    # https://developer.tuya.com/en/docs/iot/categorysp?id=Kaiuz35leyo12
    "sp": (
        TuyaLightEntityDescription(
            key=DPCode.FLOODLIGHT_SWITCH,
            brightness=DPCode.FLOODLIGHT_LIGHTNESS,
            name="Floodlight",
        ),
        TuyaLightEntityDescription(
            key=DPCode.BASIC_INDICATOR,
            name="Indicator light",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Dimmer Switch
    # https://developer.tuya.com/en/docs/iot/categorytgkg?id=Kaiuz0ktx7m0o
    "tgkg": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_1,
            translation_key="light",
            brightness=DPCode.BRIGHT_VALUE_1,
            brightness_max=DPCode.BRIGHTNESS_MAX_1,
            brightness_min=DPCode.BRIGHTNESS_MIN_1,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_2,
            translation_key="light_2",
            brightness=DPCode.BRIGHT_VALUE_2,
            brightness_max=DPCode.BRIGHTNESS_MAX_2,
            brightness_min=DPCode.BRIGHTNESS_MIN_2,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_3,
            translation_key="light_3",
            brightness=DPCode.BRIGHT_VALUE_3,
            brightness_max=DPCode.BRIGHTNESS_MAX_3,
            brightness_min=DPCode.BRIGHTNESS_MIN_3,
        ),
    ),
    # Dimmer
    # https://developer.tuya.com/en/docs/iot/tgq?id=Kaof8ke9il4k4
    "tgq": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            translation_key="light",
            brightness=(DPCode.BRIGHT_VALUE_V2, DPCode.BRIGHT_VALUE),
            brightness_max=DPCode.BRIGHTNESS_MAX_1,
            brightness_min=DPCode.BRIGHTNESS_MIN_1,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_1,
            translation_key="light",
            brightness=DPCode.BRIGHT_VALUE_1,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_2,
            translation_key="light_2",
            brightness=DPCode.BRIGHT_VALUE_2,
        ),
    ),
    # Wake Up Light II
    # Not documented
    "hxd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            translation_key="light",
            brightness=(DPCode.BRIGHT_VALUE_V2, DPCode.BRIGHT_VALUE),
            brightness_max=DPCode.BRIGHTNESS_MAX_1,
            brightness_min=DPCode.BRIGHTNESS_MIN_1,
        ),
    ),
    # Solar Light
    # https://developer.tuya.com/en/docs/iot/tynd?id=Kaof8j02e1t98
    "tyndj": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Ceiling Light
    # https://developer.tuya.com/en/docs/iot/ceiling-light?id=Kaiuz03xxfc4r
    "xdd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_NIGHT_LIGHT,
            translation_key="night_light",
        ),
    ),
    # Remote Control
    # https://developer.tuya.com/en/docs/iot/ykq?id=Kaof8ljn81aov
    "ykq": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_CONTROLLER,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_CONTROLLER,
            color_temp=DPCode.TEMP_CONTROLLER,
        ),
    ),
    # Fan
    # https://developer.tuya.com/en/docs/iot/categoryfs?id=Kaiuz1xweel1c
    "fs": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            translation_key="light_2",
            brightness=DPCode.BRIGHT_VALUE_1,
        ),
    ),
}

# Socket (duplicate of `kg`)
# https://developer.tuya.com/en/docs/iot/s?id=K9gf7o5prgf7s
LIGHTS["cz"] = LIGHTS["kg"]

# Power Socket (duplicate of `kg`)
# https://developer.tuya.com/en/docs/iot/s?id=K9gf7o5prgf7s
LIGHTS["pc"] = LIGHTS["kg"]

# update the category mapping using the product mapping overrides
# both tuple should have the same size
def update_mapping(category_description: tuple[TuyaLightEntityDescription], mapping: tuple[TuyaLightEntityDescription]) -> tuple[TuyaLightEntityDescription]:
    _LOGGER.debug("Updating mapping with category_description: %s, mapping: %s", category_description, mapping)
    m = tuple()
    l = list(category_description)
    for desc in mapping:
        cat_desc = l.pop(0)
        if desc.key == "":
            cat_desc = copy.deepcopy(cat_desc)
            
            for key in [
                        "brightness_max", 
                        "brightness_min", 
                        "color_data", 
                        "color_mode", 
                        "color_temp", 
                    ]:
                if v := getattr(desc, key):
                    setattr(cat_desc, key, v)

            for key in [
                        "function", 
                        "status_range", 
                    ]:
                if v := getattr(desc, key):
                    l = getattr(desc, key)
                    if l:
                        l.append(v)
                    else:
                        l = v
                    setattr(cat_desc, key, l)

            for key in [
                        "values_overrides", 
                        "values_defaults", 
                    ]:
                if v := getattr(desc, key):
                    l = getattr(desc, key)
                    if l:
                        l.update(v)
                    else:
                        l = v
                    setattr(cat_desc, key, l)

            desc = cat_desc

        m = m + (desc,)

    return m

def get_mapping_by_device(device: TuyaBLEDevice) -> tuple[TuyaLightEntityDescription]:
    _LOGGER.debug("Getting mapping by device: %s", device)
    category_mapping = LIGHTS.get(device.category)

    category = ProductsMapping.get(device.category)
    if category is not None:
        product_mapping_overrides = category.get(device.product_id)
        if product_mapping_overrides is not None:
             return update_mapping(category_mapping, product_mapping_overrides)
             
    return category_mapping


class TuyaBLELight(TuyaBLEEntity, LightEntity):
    """Tuya BLE light device."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        description: TuyaBLEEntityDescription,
    ) -> None:
        """Initialize the light."""
        _LOGGER.debug("Initializing TuyaBLELight with device: %s, product: %s, description: %s", device, product, description)
        super().__init__(hass, coordinator, device, product, description)
        
        self._attr_available = False
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._registered = False
        self._init_retry_count = 0
        self._max_init_retries = 3
        _LOGGER.debug("TuyaBLELight initialized with available: %s, supported_color_modes: %s", self._attr_available, self._attr_supported_color_modes)

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        _LOGGER.debug("Entity added to hass for device: %s", self._device.address)
        await super().async_added_to_hass()
        try:
            await self._verify_registration()
        except Exception as err:
            _LOGGER.error(
                "%s: Failed to verify device registration: %s",
                self._device.address,
                str(err),
                exc_info=True
            )
            self._attr_available = False
        _LOGGER.debug(
            "%s: Light entity added to HASS - unique_id: %s, registered: %s, available: %s",
            self._device.address,
            self._attr_unique_id,
            self._registered,
            self._attr_available
        )

    async def _verify_registration(self) -> None:
        """Verify device registration status."""
        _LOGGER.debug(
            "%s: Starting registration verification (attempt %d/%d)",
            self._device.address,
            self._init_retry_count + 1,
            self._max_init_retries
        )
        
        while not self._registered and self._init_retry_count < self._max_init_retries:
            try:
                async with asyncio.timeout(30):
                    _LOGGER.debug(
                        "%s: Attempting to verify registration with device",
                        self._device.address
                    )
                    
                    # Check if device is connected and authenticated
                    if not self._device.is_connected:
                        _LOGGER.debug("%s: Device not connected, attempting to connect", self._device.address)
                        await self._device.connect()
                    
                    if not await self._device.authenticate():
                        _LOGGER.error("%s: Failed to authenticate with device", self._device.address)
                        raise HomeAssistantError("Failed to authenticate with device")
                        
                    self._registered = True
                    self._attr_available = True
                    
                    _LOGGER.debug(
                        "%s: Device successfully registered and available",
                        self._device.address
                    )
                    return
                    
            except asyncio.TimeoutError:
                self._init_retry_count += 1
                _LOGGER.warning(
                    "%s: Registration verification timed out (attempt %d/%d)",
                    self._device.address,
                    self._init_retry_count,
                    self._max_init_retries
                )
            except Exception as err:
                self._init_retry_count += 1
                _LOGGER.error(
                    "%s: Failed to verify device registration: %s",
                    self._device.address,
                    self._init_retry_count,
                    self._max_init_retries,
                    str(err),
                    exc_info=True
                )
                
        if not self._registered:
            _LOGGER.error(
                "%s: Device registration verification failed after %d attempts",
                self._device.address,
                self._max_init_retries
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug(
            "%s: Turn on requested with parameters: %s",
            self._device.address,
            kwargs
        )
        
        if not self._registered:
            _LOGGER.error(
                "%s: Cannot turn on - device not registered",
                self._device.address
            )
            raise HomeAssistantError(
                f"{self._device.address}: Cannot control unregistered device"
            )
            
        try:
            _LOGGER.debug(
                "%s: Executing turn on command",
                self._device.address
            )
            await super().async_turn_on(**kwargs)
            _LOGGER.debug(
                "%s: Turn on successful",
                self._device.address
            )
        except Exception as err:
            self._attr_available = False
            self.async_write_ha_state()
            _LOGGER.error(
                "%s: Failed to turn on: %s",
                self._device.address,
                str(err),
                exc_info=True
            )
            raise HomeAssistantError(f"Failed to turn on: {str(err)}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug(
            "%s: Turn off requested",
            self._device.address
        )
        
        if not self._registered:
            _LOGGER.error(
                "%s: Cannot turn off - device not registered",
                self._device.address
            )
            raise HomeAssistantError(
                f"{self._device.address}: Cannot control unregistered device"
            )
            
        try:
            _LOGGER.debug(
                "%s: Executing turn off command",
                self._device.address
            )
            await super().async_turn_off(**kwargs)
            _LOGGER.debug(
                "%s: Turn off successful",
                self._device.address
            )
        except Exception as err:
            self._attr_available = False 
            self.async_write_ha_state()
            _LOGGER.error(
                "%s: Failed to turn off: %s",
                self._device.address,
                str(err),
                exc_info=True
            )
            raise HomeAssistantError(f"Failed to turn off: {str(err)}") from err

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "%s: Handling coordinator update - previous state: %s, new state: %s, connection state: %s",
            self._device.address,
            getattr(self, '_attr_state', 'Unknown'),
            self._device.status if hasattr(self._device, 'status') else 'Unknown',
            "Connected" if self._device.is_connected else "Disconnected"
        )
        super()._handle_coordinator_update()

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE lights."""
    _LOGGER.debug(
        "Setting up lights for device %s with product info: %s",
        entry.entry_id,
        hass.data[DOMAIN][entry.entry_id].product
    )

    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]

    try:
        descs = get_mapping_by_device(data.device)
        _LOGGER.debug(
            "%s: Got light descriptions: %s",
            data.device.address,
            descs
        )
    except Exception as e:
        _LOGGER.error(
            "%s: Failed to get light descriptions: %s",
            data.device.address,
            str(e),
            exc_info=True
        )
        return

    entities: list[TuyaBLELight] = []

    for desc in descs:
        _LOGGER.debug(
            "%s: Creating light entity with description: %s",
            data.device.address,
            desc
        )
        try:
            entity = TuyaBLELight(
                hass,
                data.coordinator,
                data.device,
                data.product,
                desc,
            )
            entities.append(entity)
            _LOGGER.debug(
                "%s: Successfully created light entity: %s",
                data.device.address,
                entity._attr_unique_id
            )
        except Exception as e:
            _LOGGER.error(
                "%s: Failed to create light entity: %s",
                data.device.address,
                str(e),
                exc_info=True
            )

    if entities:
        _LOGGER.debug(
            "%s: Adding %d light entities",
            data.device.address,
            len(entities)
        )
        try:
            async_add_entities(entities)
            _LOGGER.debug(
                "%s: Successfully added light entities to HASS",
                data.device.address
            )
        except Exception as e:
            _LOGGER.error(
                "%s: Failed to add light entities to HASS: %s",
                data.device.address,
                str(e),
                exc_info=True
            )
    else:
        _LOGGER.warning(
            "%s: No light entities created",
            data.device.address
        )
