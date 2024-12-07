from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)

@dataclass
class TuyaBLEDeviceCredentials:
    uuid: str
    local_key: str
    device_id: str
    category: str
    product_id: str
    device_name: str | None
    product_model: str | None
    product_name: str | None
    functions: list | None
    status_range: list | None

    def __str__(self):
        return (
            "uuid: xxxxxxxxxxxxxxxx, "
            "local_key: xxxxxxxxxxxxxxxx, "
            "device_id: xxxxxxxxxxxxxxxx, "
            "category: %s, "
            "product_id: %s, "
            "device_name: %s, "
            "product_model: %s, "
            "product_name: %s, "
            "functions: %s, "
            "status_range: %s"
        ) % (
            self.category,
            self.product_id,
            self.device_name,
            self.product_model,
            self.product_name,
            self.functions,
            self.status_range,
        )

class AbstractTuyaBLEDeviceManager(ABC):
    """Abstract manager of the Tuya BLE devices credentials."""

    @abstractmethod
    async def get_device_credentials(
        self,
        address: str,
        force_update: bool = False,
        save_data: bool = False,
    ) -> TuyaBLEDeviceCredentials | None:
        """Get credentials of the Tuya BLE device."""
        _LOGGER.debug("Getting device credentials for address: %s, force_update: %s, save_data: %s", address, force_update, save_data)
        pass

    @classmethod
    def check_and_create_device_credentials(
        cls,
        uuid: str | None,
        local_key: str | None,
        device_id: str | None,
        category: str | None,
        product_id: str | None,
        device_name: str | None,
        product_model: str | None,
        product_name: str | None,
        functions: list | None,
        status_range: list | None,
    ) -> TuyaBLEDeviceCredentials | None:
        """Checks and creates credentials of the Tuya BLE device."""
        _LOGGER.debug("Checking and creating device credentials with uuid: %s, local_key: %s, device_id: %s, category: %s, product_id: %s", uuid, local_key, device_id, category, product_id)
        if (
            uuid and 
            local_key and 
            device_id and
            category and
            product_id
        ):
            credentials = TuyaBLEDeviceCredentials(
                uuid,
                local_key,
                device_id,
                category,
                product_id,
                device_name,
                product_model,
                product_name,
                functions,
                status_range,
            )
            _LOGGER.debug("Device credentials created: %s", credentials)
            return credentials
        else:
            _LOGGER.warning("Failed to create device credentials due to missing information")
            return None
