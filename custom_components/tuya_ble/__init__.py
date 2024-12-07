"""The Tuya BLE integration."""
from __future__ import annotations

import logging

from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS, get_device

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .tuya_ble import TuyaBLEDevice

from .cloud import HASSTuyaBLEDeviceManager
from .const import DOMAIN
from .devices import TuyaBLECoordinator, TuyaBLEData, get_device_product_info

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TEXT,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tuya BLE from a config entry."""
    _LOGGER.debug("Setting up Tuya BLE entry: %s", entry.entry_id)
    address: str = entry.data[CONF_ADDRESS]
    _LOGGER.debug("Device address from config entry: %s", address)

    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), True
    ) or await get_device(address)
    if not ble_device:
        _LOGGER.error("Could not find Tuya BLE device with address: %s", address)
        raise ConfigEntryNotReady(
            f"Could not find Tuya BLE device with address {address}"
        )
    _LOGGER.debug("BLE device found: %s", ble_device)

    manager = HASSTuyaBLEDeviceManager(hass, entry.options.copy())
    _LOGGER.debug("Device manager initialized: %s", manager)

    device = TuyaBLEDevice(manager, ble_device)
    _LOGGER.debug("TuyaBLEDevice initialized: %s", device)

    await device.initialize()
    _LOGGER.debug("Device initialized")

    product_info = get_device_product_info(device)
    _LOGGER.debug("Product info retrieved: %s", product_info)

    coordinator = TuyaBLECoordinator(hass, device)
    _LOGGER.debug("Coordinator initialized: %s", coordinator)

    hass.add_job(device.update())
    _LOGGER.debug("Device update job added")

    @callback
    def _async_update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Update from a ble callback."""
        _LOGGER.debug("BLE callback update for device: %s", service_info.device)
        device.set_ble_device_and_advertisement_data(
            service_info.device, service_info.advertisement
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            BluetoothCallbackMatcher({ADDRESS: address}),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )
    _LOGGER.debug("BLE callback registered")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = TuyaBLEData(
        entry.title,
        device,
        product_info,
        manager,
        coordinator,
    )
    _LOGGER.debug("TuyaBLEData stored in hass.data")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Config entry setups forwarded for platforms: %s", PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.debug("Update listener added")

    async def _async_stop(event: Event) -> None:
        """Close the connection."""
        _LOGGER.debug("Stopping device: %s", device)
        await device.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )
    _LOGGER.debug("Stop listener added for Home Assistant stop event")

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Update listener triggered for entry: %s", entry.entry_id)
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    if entry.title != data.title:
        _LOGGER.debug("Entry title changed from %s to %s, reloading entry", data.title, entry.title)
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry: %s", entry.entry_id)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data: TuyaBLEData = hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Stopping device: %s", data.device)
        await data.device.stop()

    _LOGGER.debug("Config entry unloaded: %s", entry.entry_id)
    return unload_ok
