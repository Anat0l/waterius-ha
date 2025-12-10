"""Константы для интеграции Waterius."""
from typing import Final

DOMAIN: Final = "wateruis_ha"

CONF_PORT: Final = "port"
DEFAULT_PORT: Final = 9090

CONF_DEVICES: Final = "devices"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_DEVICE_MAC: Final = "device_mac"
CONF_ENABLE_LOGGING: Final = "enable_logging"
DEFAULT_ENABLE_LOGGING: Final = True
CONF_AUTO_ADD_DEVICES: Final = "auto_add_devices"
DEFAULT_AUTO_ADD_DEVICES: Final = False
CONF_CHANNEL_0_DATA_TYPE: Final = "channel_0_data_type"
CONF_CHANNEL_1_DATA_TYPE: Final = "channel_1_data_type"

