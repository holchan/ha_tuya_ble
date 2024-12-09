import asyncio
import logging
from tuya_iot import TuyaOpenAPI, AuthType

# Set up logging
logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

# Your configuration
CLOUD_CONFIG = {
    'endpoint': 'https://openapi.tuyaus.com',
    'auth_type': AuthType.SMART_HOME,
    'access_id': 'your_access_id',
    'access_secret': 'your_access_secret',
    'username': 'your_email',
    'password': 'your_password',
    'country_code': '55',
    'app_type': 'tuyaSmart'
}

async def test_tuya_auth():
    """Test authentication with Tuya cloud."""
    try:
        LOGGER.info("Initializing Tuya OpenAPI")
        
        # Initialize API
        api = TuyaOpenAPI(
            endpoint=CLOUD_CONFIG['endpoint'],
            access_id=CLOUD_CONFIG['access_id'],
            access_secret=CLOUD_CONFIG['access_secret'],
            auth_type=CLOUD_CONFIG['auth_type']
        )
        
        # Set development channel
        api.set_dev_channel("hass")

        LOGGER.info("Attempting to connect...")
        
        # Connect
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            api.connect,
            CLOUD_CONFIG['username'],
            CLOUD_CONFIG['password'],
            CLOUD_CONFIG['country_code'],
            CLOUD_CONFIG['app_type']
        )

        if response.get('success', False):
            LOGGER.info("Login successful!")
            LOGGER.info("Response: %s", response)
            return True
        else:
            LOGGER.error(
                "Login failed: Code=%s, Msg=%s",
                response.get('code'),
                response.get('msg')
            )
            return False

    except Exception as e:
        LOGGER.error("Error in authentication: %s", str(e))
        return False

def main():
    """Main function to run the test."""
    LOGGER.info("Starting Tuya authentication test")
    asyncio.run(test_tuya_auth())

if __name__ == "__main__":
    main()