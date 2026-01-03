"""Diagnostics platform для интеграции Waterius."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .device_manager import DeviceManager

if TYPE_CHECKING:
    from . import WateriusConfigEntry

# Поля, которые нужно скрыть в диагностике (конфиденциальная информация)
TO_REDACT = {"key", "email"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: "WateriusConfigEntry"
) -> dict[str, Any]:
    """Диагностика для config entry."""
    if entry.runtime_data is None:
        return {}

    device_manager: DeviceManager = entry.runtime_data.device_manager

    diagnostics_data = {
        "config_entry": {
            "auto_add_devices": entry.data.get("auto_add_devices", True),
            "devices_count": len(entry.data.get("devices", [])),
        },
    }

    if device_manager:
        devices_data = {}
        for device_id, device in device_manager.get_all_devices().items():
            device_info = {
                "device_id": device.device_id,
                "name": device.name,
                "mac": device.mac,
                "has_data": device.data is not None,
            }
            if device.data:
                device_info["data"] = async_redact_data(device.data, TO_REDACT)
            devices_data[device_id] = device_info

        diagnostics_data["devices"] = devices_data

    return diagnostics_data


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: "WateriusConfigEntry", device: dr.DeviceEntry
) -> dict[str, Any]:
    """Диагностика для конкретного устройства."""
    if entry.runtime_data is None:
        return {}

    device_manager: DeviceManager = entry.runtime_data.device_manager

    if not device_manager:
        return {}

    # Получаем device_id из идентификаторов устройства
    device_id = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            device_id = identifier[1]
            break

    if not device_id:
        return {}

    device_obj = device_manager.get_device(device_id)
    if not device_obj:
        return {}

    diagnostics_data = {
        "device_id": device_obj.device_id,
        "name": device_obj.name,
        "mac": device_obj.mac,
        "has_data": device_obj.data is not None,
    }

    if device_obj.data:
        # Добавляем все диагностические данные устройства
        device_data = device_obj.data.copy()
        
        # Структурируем данные для удобства
        diagnostics_data["data"] = async_redact_data(device_data, TO_REDACT)
        
        # Группируем данные по категориям
        diagnostics_data["categories"] = {
            "power": {
                "voltage": device_data.get("voltage"),
                "voltage_low": device_data.get("voltage_low"),
                "voltage_diff": device_data.get("voltage_diff"),
                "battery": device_data.get("battery"),
            },
            "network": {
                "channel": device_data.get("channel"),
                "wifi_phy_mode": device_data.get("wifi_phy_mode"),
                "wifi_phy_mode_s": device_data.get("wifi_phy_mode_s"),
                "router_mac": device_data.get("router_mac"),
                "rssi": device_data.get("rssi"),
                "mac": device_data.get("mac"),
                "ip": device_data.get("ip"),
                "dhcp": device_data.get("dhcp"),
            },
            "firmware": {
                "version": device_data.get("version"),
                "version_esp": device_data.get("version_esp"),
                "esp_id": device_data.get("esp_id"),
                "flash_id": device_data.get("flash_id"),
            },
            "system": {
                "freemem": device_data.get("freemem"),
                "timestamp": device_data.get("timestamp"),
                "waketime": device_data.get("waketime"),
                "period_min_tuned": device_data.get("period_min_tuned"),
                "period_min": device_data.get("period_min"),
                "setuptime": device_data.get("setuptime"),
                "boot": device_data.get("boot"),
                "resets": device_data.get("resets"),
                "mode": device_data.get("mode"),
                "setup_finished": device_data.get("setup_finished"),
                "setup_started": device_data.get("setup_started"),
                "ntp_errors": device_data.get("ntp_errors"),
            },
            "services": {
                "mqtt": device_data.get("mqtt"),
                "ha": device_data.get("ha"),
                "http": device_data.get("http"),
            },
        }

    return diagnostics_data

