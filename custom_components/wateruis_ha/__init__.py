"""Интеграция Waterius для Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_PORT,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MAC,
    CONF_ENABLE_LOGGING,
    DEFAULT_ENABLE_LOGGING,
    CONF_AUTO_ADD_DEVICES,
)
from .web_server import WateriusWebServer
from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Инициализация интеграции из config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    port = entry.data.get(CONF_PORT, 9090)
    enable_logging = entry.data.get(CONF_ENABLE_LOGGING, DEFAULT_ENABLE_LOGGING)
    # Автоматическое добавление устройств всегда включено
    auto_add_devices = entry.data.get(CONF_AUTO_ADD_DEVICES, True)
    
    # Создаем менеджер устройств
    device_manager = DeviceManager(hass)
    
    # Загружаем устройства из конфигурации
    devices = entry.data.get(CONF_DEVICES, [])
    for device_config in devices:
        device_id = device_config.get(CONF_DEVICE_ID)
        device_name = device_config.get(CONF_DEVICE_NAME)
        device_mac = device_config.get(CONF_DEVICE_MAC)
        if device_id and device_name:
            device_manager.add_device(device_id, device_name, device_mac)
            _LOGGER.info(
                "Загружено устройство: %s (%s)%s",
                device_name,
                device_id,
                f" с MAC {device_mac}" if device_mac else ""
            )
    
    # Создаем и запускаем веб-сервер с менеджером устройств и настройками
    web_server = WateriusWebServer(hass, port, device_manager, enable_logging, auto_add_devices, entry)
    try:
        await web_server.start()
    except OSError as e:
        if "address in use" in str(e) or "Port" in str(e) and "is already in use" in str(e):
            _LOGGER.error(
                "Не удалось запустить веб-сервер на порту %s: порт занят. "
                "Пожалуйста, измените порт в настройках интеграции.",
                port
            )
        raise
    
    # Сохраняем веб-сервер и менеджер устройств в hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "web_server": web_server,
        "device_manager": device_manager,
    }
    
    # Регистрируем платформы (если будут нужны в будущем)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info(
        "Интеграция Waterius инициализирована на порту %s с %d устройствами",
        port,
        len(devices)
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции."""
    # Останавливаем веб-сервер
    if entry.entry_id in hass.data[DOMAIN]:
        entry_data = hass.data[DOMAIN][entry.entry_id]
        web_server = entry_data.get("web_server")
        if web_server:
            await web_server.stop()
        del hass.data[DOMAIN][entry.entry_id]
    
    # Выгружаем платформы
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        _LOGGER.info("Интеграция Waterius выгружена")
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Перезагрузка интеграции."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)

