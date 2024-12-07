"""Config flow for Tuya BLE integration."""

from __future__ import annotations

import logging
import pycountry
from typing import Any

import voluptuous as vol
from tuya_iot import AuthType

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import (
    CONF_ADDRESS, 
    CONF_DEVICE_ID,
    CONF_COUNTRY_CODE,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowHandler, FlowResult

from .tuya_ble import SERVICE_UUID, TuyaBLEDeviceCredentials

from .const import (
    TUYA_COUNTRIES,
    TUYA_SMART_APP,
    SMARTLIFE_APP,
    TUYA_RESPONSE_SUCCESS,
    TUYA_RESPONSE_CODE,
    TUYA_RESPONSE_MSG,
    CONF_ACCESS_ID,
    CONF_ACCESS_SECRET,
    CONF_APP_TYPE,
    CONF_AUTH_TYPE,
    CONF_ENDPOINT,
    DOMAIN,
)
from .devices import TuyaBLEData, get_device_readable_name
from .cloud import HASSTuyaBLEDeviceManager

_LOGGER = logging.getLogger(__name__)


async def _try_login(
    manager: HASSTuyaBLEDeviceManager,
    user_input: dict[str, Any],
    errors: dict[str, str],
    placeholders: dict[str, Any],
) -> dict[str, Any] | None:
    _LOGGER.debug("Attempting login with user input: %s", user_input)
    response: dict[Any, Any] | None
    data: dict[str, Any]

    try:
        country = [
            country
            for country in TUYA_COUNTRIES
            if country.name == user_input[CONF_COUNTRY_CODE]
        ][0]
        _LOGGER.debug("Selected country: %s", country)
    except IndexError:
        _LOGGER.error("Country code not found in TUYA_COUNTRIES: %s", user_input[CONF_COUNTRY_CODE])
        errors["base"] = "invalid_country_code"
        return None

    data = {
        CONF_ENDPOINT: country.endpoint,
        CONF_AUTH_TYPE: AuthType.CUSTOM,
        CONF_ACCESS_ID: user_input[CONF_ACCESS_ID],
        CONF_ACCESS_SECRET: user_input[CONF_ACCESS_SECRET],
        CONF_USERNAME: user_input[CONF_USERNAME],
        CONF_PASSWORD: user_input[CONF_PASSWORD],
        CONF_COUNTRY_CODE: country.country_code,
    }
    _LOGGER.debug("Login data prepared: %s", data)

    for app_type in (TUYA_SMART_APP, SMARTLIFE_APP, ""):
        data[CONF_APP_TYPE] = app_type
        if app_type == "":
            data[CONF_AUTH_TYPE] = AuthType.CUSTOM
        else:
            data[CONF_AUTH_TYPE] = AuthType.SMART_HOME

        _LOGGER.debug("Attempting login with app type: %s", app_type)
        response = await manager._login(data, True)
        _LOGGER.debug("Login response: %s", response)

        if response.get(TUYA_RESPONSE_SUCCESS, False):
            _LOGGER.debug("Login successful with app type: %s", app_type)
            return data

    errors["base"] = "login_error"
    if response:
        placeholders.update(
            {
                TUYA_RESPONSE_CODE: response.get(TUYA_RESPONSE_CODE),
                TUYA_RESPONSE_MSG: response.get(TUYA_RESPONSE_MSG),
            }
        )
        _LOGGER.debug("Login failed with response code: %s, message: %s", 
                      response.get(TUYA_RESPONSE_CODE), response.get(TUYA_RESPONSE_MSG))

    return None


async def _show_login_form(
    flow: ConfigFlow,
    user_input: dict[str, Any] | None,
    errors: dict[str, str],
    placeholders: dict[str, str],
) -> FlowResult:
    """Show the login form."""
    _LOGGER.debug("Showing login form with user input: %s, errors: %s", user_input, errors)
    if user_input is None:
        user_input = {}

    def_country_name: str | None = None
    try:
        def _get_country():
            country = pycountry.countries.get(alpha_2=flow.hass.config.country)
            return country.name if country else None
        
        def_country_name = await flow.hass.async_add_executor_job(_get_country)
        _LOGGER.debug("Default country name determined: %s", def_country_name)
    except Exception as e:
        _LOGGER.error("Error determining default country name: %s", e)

    return flow.async_show_form(
        step_id="login",
        data_schema=vol.Schema({
            vol.Required(
                CONF_COUNTRY_CODE,
                default=user_input.get(CONF_COUNTRY_CODE, def_country_name),
            ): vol.In([country.name for country in TUYA_COUNTRIES]),
            vol.Required(
                CONF_ACCESS_ID,
                default=user_input.get(CONF_ACCESS_ID, "")
            ): str,
            vol.Required(
                CONF_ACCESS_SECRET,
                default=user_input.get(CONF_ACCESS_SECRET, ""),
            ): str,
            vol.Required(
                CONF_USERNAME,
                default=user_input.get(CONF_USERNAME, "")
            ): str,
            vol.Required(
                CONF_PASSWORD,
                default=user_input.get(CONF_PASSWORD, "")
            ): str,
        }),
        errors=errors,
        description_placeholders=placeholders,
    )


class TuyaBLEOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle a Tuya BLE options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        _LOGGER.debug("Initialized TuyaBLEOptionsFlow with config entry: %s", config_entry)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        _LOGGER.debug("Options flow init step with user input: %s", user_input)
        return await self.async_step_login(user_input)

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the Tuya IOT platform login step."""
        _LOGGER.debug("Options flow login step with user input: %s", user_input)
        errors = {}
        placeholders = {}
        credentials: TuyaBLEDeviceCredentials | None = None
        address: str | None = self.config_entry.data.get(CONF_ADDRESS)

        if user_input is not None:
            entry: TuyaBLEData | None = None
            domain_data = self.hass.data.get(DOMAIN)
            _LOGGER.debug("Domain data retrieved: %s", domain_data)
            if domain_data:
                entry = domain_data.get(self.config_entry.entry_id)
            if entry:
                _LOGGER.debug("Entry found: %s", entry)
                login_data = await _try_login(
                    entry.manager,
                    user_input,
                    errors,
                    placeholders,
                )
                if login_data:
                    _LOGGER.debug("Login data obtained: %s", login_data)
                    credentials = await entry.manager.get_device_credentials(
                        address, True, True
                    )
                    if credentials:
                        _LOGGER.debug("Device credentials obtained: %s", credentials)
                        return self.async_create_entry(
                            title=self.config_entry.title,
                            data=entry.manager.data,
                        )
                    else:
                        _LOGGER.debug("Device not registered")
                        errors["base"] = "device_not_registered"

        if user_input is None:
            user_input = {}
            user_input.update(self.config_entry.options)
            _LOGGER.debug("User input updated with config entry options: %s", user_input)

        return _show_login_form(self, user_input, errors, placeholders)


class TuyaBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tuya BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._data: dict[str, Any] = {}
        self._manager: HASSTuyaBLEDeviceManager | None = None
        self._get_device_info_error = False
        _LOGGER.debug("Initialized TuyaBLEConfigFlow")

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Bluetooth discovery step with discovery info: %s", discovery_info)
        _LOGGER.debug("Discovery service_data: %s", discovery_info.service_data)
        _LOGGER.debug("Discovery service_uuids: %s", discovery_info.service_uuids)
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Bluetooth discovery step with discovery info: %s", discovery_info)
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)
            _LOGGER.debug("Manager initialized: %s", self._manager)
        await self._manager.build_cache()
        _LOGGER.debug("Cache built for manager")
        self.context["title_placeholders"] = {
            "name": await get_device_readable_name(
                discovery_info,
                self._manager,
            )
        }
        _LOGGER.debug("Title placeholders set: %s", self.context["title_placeholders"])
        return await self.async_step_login()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step."""
        _LOGGER.debug("User step with user input: %s", user_input)
        if user_input is None:
            # Initialize manager before proceeding to login step
            if self._manager is None:
                self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)
                _LOGGER.debug("Manager initialized: %s", self._manager)
            await self._manager.build_cache()
            _LOGGER.debug("Cache built for manager")
            return await self.async_step_login()

        # Rest of the method remains unchanged
        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)
            _LOGGER.debug("Manager initialized: %s", self._manager)
        await self._manager.build_cache()
        _LOGGER.debug("Cache built for manager")
        return await self.async_step_login()

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the Tuya IOT platform login step."""
        _LOGGER.debug("Login step with user input: %s", user_input)
        data: dict[str, Any] | None = None
        errors: dict[str, str] = {}
        placeholders: dict[str, Any] = {}

        # Ensure manager is initialized
        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)
            await self._manager.build_cache()
            _LOGGER.debug("Manager initialized and cache built")

        if user_input is not None:
            data = await _try_login(
                self._manager,
                user_input,
                errors,
                placeholders,
            )
            if data:
                _LOGGER.debug("Login data obtained: %s", data)
                self._data.update(data)
                if self._discovery_info is not None:
                    _LOGGER.debug("Discovery service_data: %s", self._discovery_info.service_data)
                else:
                    _LOGGER.debug("No discovery info available")
                _LOGGER.debug("SERVICE_UUID: %s", SERVICE_UUID)
                return await self.async_step_device()

        if user_input is None:
            user_input = {}
            if self._discovery_info:
                await self._manager.get_device_credentials(
                    self._discovery_info.address,
                    False,
                    True,
                )
                _LOGGER.debug("Device credentials obtained for discovery info")
            if self._data is None or len(self._data) == 0:
                self._manager.get_login_from_cache()
                _LOGGER.debug("Login data retrieved from cache")
            if self._data is not None and len(self._data) > 0:
                user_input.update(self._data)
                _LOGGER.debug("User input updated with cached data: %s", user_input)

        return await _show_login_form(self, user_input, errors, placeholders)

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        _LOGGER.debug("Device step with user input: %s", user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            local_name = await get_device_readable_name(discovery_info, self._manager)
            _LOGGER.debug("Device selected: %s, local name: %s", address, local_name)
            await self.async_set_unique_id(
                discovery_info.address, raise_on_progress=False
            )
            self._abort_if_unique_id_configured()
            credentials = await self._manager.get_device_credentials(
                discovery_info.address, self._get_device_info_error, True
            )
            self._data[CONF_ADDRESS] = discovery_info.address
            if credentials is None:
                self._get_device_info_error = True
                errors["base"] = "device_not_registered"
                _LOGGER.debug("Device not registered, credentials not found")
            else:
                _LOGGER.debug("Device credentials obtained: %s", credentials)
                return self.async_create_entry(
                    title=local_name,
                    data={CONF_ADDRESS: discovery_info.address},
                    options=self._data,
                )

        if discovery := self._discovery_info:
            self._discovered_devices[discovery.address] = discovery
            _LOGGER.debug("Discovery info added to discovered devices: %s", discovery)
        else:
            current_addresses = self._async_current_ids()
            _LOGGER.debug("Current addresses: %s", current_addresses)
            for discovery in async_discovered_service_info(self.hass):
                _LOGGER.debug("Evaluating discovery: %s", discovery)
                _LOGGER.debug("Discovery service_data: %s", discovery.service_data)
                _LOGGER.debug("Discovery service_uuids: %s", discovery.service_uuids)
                
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                    or discovery.service_data is None
                    or not SERVICE_UUID in discovery.service_data.keys()
                ):
                    _LOGGER.debug(
                        "Skipping device %s: already configured=%s, already discovered=%s, no service data=%s, no service uuid=%s",
                        discovery.address,
                        discovery.address in current_addresses,
                        discovery.address in self._discovered_devices,
                        discovery.service_data is None,
                        not SERVICE_UUID in discovery.service_data.keys() if discovery.service_data else True
                    )
                    continue
                self._discovered_devices[discovery.address] = discovery
                _LOGGER.debug("Discovered device added: %s", discovery)

        if not self._discovered_devices:
            _LOGGER.debug("Current addresses: %s", current_addresses)
            _LOGGER.debug("Discovered devices: %s", self._discovered_devices)
            _LOGGER.debug("No unconfigured devices found, aborting")
            return self.async_abort(reason="no_unconfigured_devices")

        def_address: str
        if user_input:
            def_address = user_input.get(CONF_ADDRESS)
        else:
            def_address = list(self._discovered_devices)[0]
        _LOGGER.debug("Default address for device selection: %s", def_address)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ADDRESS,
                        default=def_address,
                    ): vol.In(
                        {
                            service_info.address: await get_device_readable_name(
                                service_info,
                                self._manager,
                            )
                            for service_info in self._discovered_devices.values()
                        }
                    ),
                },
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TuyaBLEOptionsFlow:
        """Get the options flow for this handler."""
        _LOGGER.debug("Getting options flow for config entry: %s", config_entry)
        return TuyaBLEOptionsFlow(config_entry)
