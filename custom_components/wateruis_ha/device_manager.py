"""Менеджер устройств для интеграции Waterius."""
from __future__ import annotations

import logging
from typing import Any
from dataclasses import dataclass, asdict
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)


@dataclass
class WateriusDevice:
    """Класс для представления устройства Waterius."""

    device_id: str
    name: str
    mac: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Преобразование в словарь."""
        return asdict(self)


class DeviceManager:
    """Менеджер для управления устройствами Waterius."""

    def __init__(self, hass):
        """Инициализация менеджера устройств."""
        self.hass = hass
        self._devices: dict[str, WateriusDevice] = {}
        self._devices_by_mac: dict[str, WateriusDevice] = {}
        self._update_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

    def add_device(self, device_id: str, name: str, mac: str | None = None) -> bool:
        """Добавление устройства."""
        if device_id in self._devices:
            _LOGGER.warning("Устройство с ID %s уже существует", device_id)
            return False

        device = WateriusDevice(device_id=device_id, name=name, mac=mac)
        self._devices[device_id] = device
        
        # Добавляем в индекс по MAC адресу, если указан
        if mac:
            mac_upper = mac.upper()
            self._devices_by_mac[mac_upper] = device
            _LOGGER.info("Добавлено устройство: %s (%s) с MAC %s", name, device_id, mac)
        else:
            _LOGGER.info("Добавлено устройство: %s (%s)", name, device_id)
        return True

    def remove_device(self, device_id: str) -> bool:
        """Удаление устройства."""
        if device_id not in self._devices:
            _LOGGER.warning("Устройство с ID %s не найдено", device_id)
            return False

        device = self._devices.pop(device_id)
        
        # Удаляем из индекса по MAC адресу
        if device.mac:
            mac_upper = device.mac.upper()
            self._devices_by_mac.pop(mac_upper, None)
        
        _LOGGER.info("Удалено устройство: %s (%s)", device.name, device_id)
        return True

    def get_device(self, device_id: str) -> WateriusDevice | None:
        """Получение устройства по ID."""
        return self._devices.get(device_id)

    def get_device_by_mac(self, mac: str) -> WateriusDevice | None:
        """Получение устройства по MAC адресу."""
        mac_upper = mac.upper()
        return self._devices_by_mac.get(mac_upper)

    def get_all_devices(self) -> dict[str, WateriusDevice]:
        """Получение всех устройств."""
        return self._devices.copy()

    def update_device_data(self, device_id: str, data: dict[str, Any]) -> bool:
        """Обновление данных устройства."""
        if device_id not in self._devices:
            _LOGGER.warning("Устройство с ID %s не найдено", device_id)
            return False

        device = self._devices[device_id]
        device.data = data

        # Вызываем колбэки обновления
        for callback in self._update_callbacks:
            try:
                callback(device_id, data)
            except Exception as e:
                _LOGGER.error("Ошибка в колбэке обновления устройства: %s", e)

        # Отправляем событие в Home Assistant
        self.hass.bus.async_fire(
            "waterius_device_update",
            {
                "device_id": device_id,
                "device_name": device.name,
                "data": data,
            }
        )

        _LOGGER.debug("Обновлены данные устройства %s: %s", device_id, data)
        return True

    def register_update_callback(
        self, callback: Callable[[str, dict[str, Any]], None]
    ) -> None:
        """Регистрация колбэка для обновлений устройств."""
        self._update_callbacks.append(callback)

    def get_devices_list(self) -> list[dict[str, Any]]:
        """Получение списка устройств в виде словарей."""
        return [
            {
                "device_id": device.device_id,
                "name": device.name,
                "mac": device.mac,
                "has_data": device.data is not None,
            }
            for device in self._devices.values()
        ]

