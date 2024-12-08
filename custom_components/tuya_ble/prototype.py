"""Test script for Tuya BLE beacon protocol."""
from __future__ import annotations

import asyncio
import logging
from .cloud import HASSTuyaBLEDeviceManager

# Set up logging
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

# Device configuration
DEVICE_INFO = {
    "mac": "DC:23:50:CF:CB:6A",
    "device_id": "eb4e6cocypjwgnxo",
    "local_key": "399914473589C1E2",
    "category": "dj"
}

# Cloud configuration
CLOUD_CONFIG = {
    "endpoint": "https://openapi.tuyaus.com",  # For Brazil
    "access_id": "a9938eqhp5uvx5xkd8xr",
    "access_secret": "5712bb5a33754642a185910e9c519b6b",
    "username": "holchansgomes@gmail.com",
    "password": "@Velozes1"
}

async def test_cloud_auth():
    """Test cloud authentication."""
    _LOGGER.debug("Starting cloud authentication test")
    
    try:
        # Initialize device manager
        _LOGGER.debug("Initializing device manager with config: %s", CLOUD_CONFIG)
        device_manager = HASSTuyaBLEDeviceManager(
            hass=None,  # We'll mock this
            data=CLOUD_CONFIG
        )
        
        # Test authentication
        _LOGGER.info("Attempting to authenticate with Tuya cloud...")
        response = await device_manager.login(add_to_cache=True)
        _LOGGER.debug("Auth response: %s", response)
        
        if response.get('success'):
            _LOGGER.info("Login successful")
        else:
            _LOGGER.warning("Login failed: %s", response)
        
        return device_manager
        
    except Exception as e:
        _LOGGER.error("Authentication failed with error: %s", str(e), exc_info=True)
        return None

async def test_get_beacon_key(device_manager, device_mac):
    """Test retrieving beacon key."""
    _LOGGER.debug("Starting beacon key retrieval test for device: %s", device_mac)
    
    try:
        # Get device credentials including beacon key
        _LOGGER.info("Attempting to get device credentials...")
        credentials = await device_manager.get_device_credentials(
            address=device_mac,
            force_update=True
        )
        _LOGGER.debug("Retrieved credentials: %s", credentials)
        
        return credentials
        
    except Exception as e:
        _LOGGER.error("Failed to get beacon key: %s", str(e), exc_info=True)
        return None

async def test_device_control(credentials):
    """Test basic device control."""
    _LOGGER.debug("Starting device control test with credentials: %s", credentials)
    
    try:
        # Here we'll implement basic device control using the beacon protocol
        # This will be based on the SDK implementation
        _LOGGER.info("Device control test - to be implemented")
        pass
        
    except Exception as e:
        _LOGGER.error("Device control failed: %s", str(e), exc_info=True)

async def main_function():
    """Main test function."""
    _LOGGER.info("Starting Tuya BLE beacon protocol test")
    
    try:
        # Test cloud authentication
        _LOGGER.info("Step 1: Testing cloud authentication")
        device_manager = await test_cloud_auth()
        if not device_manager:
            _LOGGER.error("Failed to initialize device manager")
            return
        
        # Test getting beacon key
        _LOGGER.info("Step 2: Testing beacon key retrieval")
        credentials = await test_get_beacon_key(device_manager, DEVICE_INFO["mac"])
        if not credentials:
            _LOGGER.error("Failed to get device credentials")
            return
        
        # Test device control
        _LOGGER.info("Step 3: Testing device control")
        await test_device_control(credentials)
        
    except Exception as e:
        _LOGGER.error("Test failed with error: %s", str(e), exc_info=True)
    
    _LOGGER.info("Test completed")

async def main():
    """Main test function."""
    await main_function()

if __name__ == "__main__":
    # Set up console logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    _LOGGER.addHandler(console_handler)
    
    # Run the test
    asyncio.run(main())