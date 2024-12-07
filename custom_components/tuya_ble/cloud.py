"""The Tuya BLE integration."""
from __future__ import annotations

import logging

from dataclasses import dataclass
import json
from typing import Any, Iterable

from homeassistant.const import (
    CONF_ADDRESS, 
    CONF_DEVICE_ID,
    CONF_COUNTRY_CODE,
    CONF_PASSWORD,
    CONF_USERNAME,
)

from homeassistant.core import HomeAssistant

from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from tuya_iot import (
    TuyaOpenAPI,
    AuthType,
    TuyaOpenMQ,
)

from .tuya_ble import (
    AbstractTuyaBLEDeviceManager,
    TuyaBLEDevice,
    TuyaBLEDeviceCredentials,
)

from .const import (
    TUYA_DOMAIN,
    CONF_ACCESS_ID,
    CONF_ACCESS_SECRET,
    CONF_APP_TYPE,
    CONF_AUTH_TYPE,
    CONF_ENDPOINT,
    CONF_PRODUCT_MODEL,
    CONF_UUID,
    CONF_LOCAL_KEY,
    CONF_CATEGORY,
    CONF_PRODUCT_ID,
    CONF_DEVICE_NAME,
    CONF_PRODUCT_NAME,
    CONF_FUNCTIONS,
    CONF_STATUS_RANGE,
    DOMAIN,
    TUYA_API_DEVICES_URL,
    TUYA_API_FACTORY_INFO_URL,
    TUYA_API_DEVICE_SPECIFICATION,
    TUYA_FACTORY_INFO_MAC,
    TUYA_RESPONSE_RESULT,
    TUYA_RESPONSE_SUCCESS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class TuyaCloudCacheItem:
    api: TuyaOpenAPI | None
    login: dict[str, Any]
    credentials: dict[str, dict[str, Any]]


CONF_TUYA_LOGIN_KEYS = [
    CONF_ENDPOINT,
    CONF_ACCESS_ID,
    CONF_ACCESS_SECRET,
    CONF_AUTH_TYPE,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_COUNTRY_CODE,
    CONF_APP_TYPE,
]

CONF_TUYA_DEVICE_KEYS = [
    CONF_UUID,
    CONF_LOCAL_KEY,
    CONF_DEVICE_ID,
    CONF_CATEGORY,
    CONF_PRODUCT_ID,
    CONF_DEVICE_NAME,
    CONF_PRODUCT_NAME,
    CONF_PRODUCT_MODEL,
]

_cache: dict[str, TuyaCloudCacheItem] = {}


class HASSTuyaBLEDeviceManager(AbstractTuyaBLEDeviceManager):
    """Cloud connected manager of the Tuya BLE devices credentials."""

    def __init__(self, hass: HomeAssistant, data: dict[str, Any]) -> None:
        assert hass is not None
        self._hass = hass
        self._data = data
        _LOGGER.debug("Initialized HASSTuyaBLEDeviceManager with data: %s", data)

    @staticmethod
    def _is_login_success(response: dict[Any, Any]) -> bool:
        success = bool(response.get(TUYA_RESPONSE_SUCCESS, False))
        _LOGGER.debug("Login success check: %s", success)
        return success

    @staticmethod
    def _get_cache_key(data: dict[str, Any]) -> str:
        key_dict = {key: data.get(key) for key in CONF_TUYA_LOGIN_KEYS}
        cache_key = json.dumps(key_dict)
        _LOGGER.debug("Generated cache key: %s", cache_key)
        return cache_key

    @staticmethod
    def _has_login(data: dict[Any, Any]) -> bool:
        has_login = all(data.get(key) is not None for key in CONF_TUYA_LOGIN_KEYS)
        _LOGGER.debug("Has login: %s", has_login)
        return has_login

    @staticmethod
    def _has_credentials(data: dict[Any, Any]) -> bool:
        has_credentials = all(data.get(key) is not None for key in CONF_TUYA_DEVICE_KEYS)
        _LOGGER.debug("Has credentials: %s", has_credentials)
        return has_credentials

    async def _login(self, data: dict[str, Any], add_to_cache: bool) -> dict[Any, Any]:
        """Login into Tuya cloud using credentials from data dictionary."""
        global _cache
        _LOGGER.debug("Attempting login with data: %s", data)

        if len(data) == 0:
            _LOGGER.warning("Empty data provided for login.")
            return {}

        api = TuyaOpenAPI(
            endpoint=data.get(CONF_ENDPOINT, ""),
            access_id=data.get(CONF_ACCESS_ID, ""),
            access_secret=data.get(CONF_ACCESS_SECRET, ""),
            auth_type=data.get(CONF_AUTH_TYPE, ""),
        )
        api.set_dev_channel("hass")
        _LOGGER.debug("TuyaOpenAPI initialized with endpoint: %s", data.get(CONF_ENDPOINT, ""))

        try:
            response = await self._hass.async_add_executor_job(
                api.connect,
                data.get(CONF_USERNAME, ""),
                data.get(CONF_PASSWORD, ""),
                data.get(CONF_COUNTRY_CODE, ""),
                data.get(CONF_APP_TYPE, ""),
            )
            _LOGGER.debug("Login response: %s", response)
        except Exception as e:
            _LOGGER.error("Error during login: %s", e)
            return {}

        if self._is_login_success(response):
            _LOGGER.info("Successful login for %s", data[CONF_USERNAME])
            if add_to_cache:
                auth_type = data[CONF_AUTH_TYPE]
                if isinstance(auth_type, AuthType):
                    data[CONF_AUTH_TYPE] = auth_type.value
                cache_key = self._get_cache_key(data)
                cache_item = _cache.get(cache_key)
                if cache_item:
                    cache_item.api = api
                    cache_item.login = data
                    _LOGGER.debug("Updated cache item for key: %s", cache_key)
                else:
                    _cache[cache_key] = TuyaCloudCacheItem(api, data, {})
                    _LOGGER.debug("Added new cache item for key: %s", cache_key)

        return response

    def _check_login(self) -> bool:
        cache_key = self._get_cache_key(self._data)
        login_exists = _cache.get(cache_key) is not None
        _LOGGER.debug("Check login for cache key %s: %s", cache_key, login_exists)
        return login_exists

    async def login(self, add_to_cache: bool = False) -> dict[Any, Any]:
        _LOGGER.debug("Performing login with add_to_cache=%s", add_to_cache)
        return await self._login(self._data, add_to_cache)

    async def _fill_cache_item(self, item: TuyaCloudCacheItem) -> None:
        _LOGGER.debug("Filling cache item for API token: %s", item.api.token_info.uid)
        try:
            devices_response = await self._hass.async_add_executor_job(
                item.api.get,
                TUYA_API_DEVICES_URL % (item.api.token_info.uid),
            )
            _LOGGER.debug("Devices response: %s", devices_response)
        except Exception as e:
            _LOGGER.error("Error fetching devices: %s", e)
            return

        if devices_response.get(TUYA_RESPONSE_RESULT):
            devices = devices_response.get(TUYA_RESPONSE_RESULT)
            if isinstance(devices, Iterable):
                for device in devices:
                    _LOGGER.debug("Processing device: %s", device)
                    try:
                        fi_response = await self._hass.async_add_executor_job(
                            item.api.get,
                            TUYA_API_FACTORY_INFO_URL % (device.get("id")),
                        )
                        _LOGGER.debug("Factory info response: %s", fi_response)
                    except Exception as e:
                        _LOGGER.error("Error fetching factory info for device %s: %s", device.get("id"), e)
                        continue

                    fi_response_result = fi_response.get(TUYA_RESPONSE_RESULT)
                    if fi_response_result and len(fi_response_result) > 0:
                        factory_info = fi_response_result[0]
                        if factory_info and (TUYA_FACTORY_INFO_MAC in factory_info):
                            mac = ":".join(
                                factory_info[TUYA_FACTORY_INFO_MAC][i : i + 2]
                                for i in range(0, 12, 2)
                            ).upper()
                            _LOGGER.debug("Parsed MAC address: %s", mac)
                            item.credentials[mac] = {
                                CONF_ADDRESS: mac,
                                CONF_UUID: device.get("uuid"),
                                CONF_LOCAL_KEY: device.get("local_key"),
                                CONF_DEVICE_ID: device.get("id"),
                                CONF_CATEGORY: device.get("category"),
                                CONF_PRODUCT_ID: device.get("product_id"),
                                CONF_DEVICE_NAME: device.get("name"),
                                CONF_PRODUCT_MODEL: device.get("model"),
                                CONF_PRODUCT_NAME: device.get("product_name"),
                            }
                            _LOGGER.debug("Updated credentials for MAC: %s", mac)

                            try:
                                spec_response = await self._hass.async_add_executor_job(
                                    item.api.get,
                                    TUYA_API_DEVICE_SPECIFICATION % device.get("id")
                                )
                                _LOGGER.debug("Specification response: %s", spec_response)
                            except Exception as e:
                                _LOGGER.error("Error fetching specification for device %s: %s", device.get("id"), e)
                                continue

                            spec_response_result = spec_response.get(TUYA_RESPONSE_RESULT)
                            if spec_response_result:
                                functions = spec_response_result.get("functions")
                                if functions:
                                    item.credentials[mac][CONF_FUNCTIONS] = functions
                                    _LOGGER.debug("Updated functions for MAC: %s", mac)
                                status = spec_response_result.get("status")
                                if status:
                                    item.credentials[mac][CONF_STATUS_RANGE] = status
                                    _LOGGER.debug("Updated status range for MAC: %s", mac)

    async def build_cache(self) -> None:
        global _cache
        _LOGGER.debug("Building cache...")
        data = {}
        tuya_config_entries = self._hass.config_entries.async_entries(TUYA_DOMAIN)
        for config_entry in tuya_config_entries:
            data.clear()
            data.update(config_entry.data)
            _LOGGER.debug("Processing Tuya config entry: %s", config_entry.entry_id)
            key = self._get_cache_key(data)
            item = _cache.get(key)
            if item is None or len(item.credentials) == 0:
                if self._is_login_success(await self._login(data, True)):
                    item = _cache.get(key)
                    if item and len(item.credentials) == 0:
                        await self._fill_cache_item(item)

        ble_config_entries = self._hass.config_entries.async_entries(DOMAIN)
        for config_entry in ble_config_entries:
            data.clear()
            data.update(config_entry.options)
            _LOGGER.debug("Processing BLE config entry: %s", config_entry.entry_id)
            key = self._get_cache_key(data)
            item = _cache.get(key)
            if item is None or len(item.credentials) == 0:
                if self._is_login_success(await self._login(data, True)):
                    item = _cache.get(key)
                    if item and len(item.credentials) == 0:
                        await self._fill_cache_item(item)

    def get_login_from_cache(self) -> None:
        global _cache
        _LOGGER.debug("Retrieving login from cache...")
        for cache_item in _cache.values():
            self._data.update(cache_item.login)
            _LOGGER.debug("Updated data with login: %s", cache_item.login)
            break

    async def get_device_credentials(
        self,
        address: str,
        force_update: bool = False,
        save_data: bool = False,
    ) -> TuyaBLEDeviceCredentials | None:
        """Get credentials of the Tuya BLE device."""
        global _cache
        _LOGGER.debug("Attempting to get credentials for device: %s", address)
        _LOGGER.debug("Cache contents: %s", _cache)
        _LOGGER.debug("Getting device credentials for address: %s", address)
        item: TuyaCloudCacheItem | None = None
        credentials: dict[str, any] | None = None
        result: TuyaBLEDeviceCredentials | None = None

        if not force_update and self._has_credentials(self._data):
            credentials = self._data.copy()
            _LOGGER.debug("Using existing credentials from data.")
        else:
            cache_key: str | None = None
            if self._has_login(self._data):
                cache_key = self._get_cache_key(self._data)
            else:
                for key in _cache.keys():
                    if _cache[key].credentials.get(address) is not None:
                        cache_key = key
                        break
            if cache_key:
                item = _cache.get(cache_key)
                _LOGGER.debug("Found cache item for key: %s", cache_key)

            if item is None or force_update:
                if self._is_login_success(await self.login(True)):
                    item = _cache.get(cache_key)
                    if item:
                        await self._fill_cache_item(item)

            if item:
                credentials = item.credentials.get(address)
                _LOGGER.debug("Retrieved credentials for address: %s", address)

        if credentials:
            result = TuyaBLEDeviceCredentials(
                credentials.get(CONF_UUID, ""),
                credentials.get(CONF_LOCAL_KEY, ""),
                credentials.get(CONF_DEVICE_ID, ""),
                credentials.get(CONF_CATEGORY, ""),
                credentials.get(CONF_PRODUCT_ID, ""),
                credentials.get(CONF_DEVICE_NAME, ""),
                credentials.get(CONF_PRODUCT_MODEL, ""),
                credentials.get(CONF_PRODUCT_NAME, ""),
                credentials.get(CONF_FUNCTIONS, []),
                credentials.get(CONF_STATUS_RANGE, []),
            )
            _LOGGER.debug("Retrieved: %s", result)
            if save_data:
                if item:
                    self._data.update(item.login)
                self._data.update(credentials)
                _LOGGER.debug("Updated data with credentials.")

        return result

    @property
    def data(self) -> dict[str, Any]:
        _LOGGER.debug("Accessing data property.")
        return self._data
