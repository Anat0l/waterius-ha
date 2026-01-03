"""Менеджер устройств для интеграции Waterius."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from dataclasses import dataclass, asdict, field
from collections.abc import Callable

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class WateriusDevice:
    """Класс для представления устройства Waterius."""

    device_id: str
    name: str
    mac: str | None = None
    data: dict[str, Any] | None = None
    last_update_time: datetime | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        """Преобразование в словарь."""
        return asdict(self)


class DeviceManager:
    """Менеджер для управления устройствами Waterius."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Инициализация менеджера устройств.
        
        Args:
            hass: Экземпляр Home Assistant
        """
        self.hass: HomeAssistant = hass
        self._devices: dict[str, WateriusDevice] = {}
        self._devices_by_mac: dict[str, WateriusDevice] = {}
        self._update_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

    def add_device(self, device_id: str, name: str, mac: str | None = None) -> bool:
        """Добавление устройства.
        
        Args:
            device_id: Уникальный ID устройства
            name: Имя устройства
            mac: MAC адрес устройства (опционально)
            
        Returns:
            True если устройство успешно добавлено, False если уже существует
        """
        if device_id in self._devices:
            _LOGGER.warning("Устройство с ID %s уже существует", device_id)
            return False

        device = WateriusDevice(device_id=device_id, name=name, mac=mac)
        
        # Инициализируем device.data ПУСТЫМ словарем
        # Значения будут установлены при первом получении данных от устройства
        # Это позволяет select'ам корректно определить приоритет данных:
        # - Если device.data пустой и нет last_update_time → используется сохраненное состояние
        # - Если device.data заполнен и есть last_update_time → используются данные от устройства
        device.data = {}
        
        self._devices[device_id] = device
        
        # Добавляем в индекс по MAC адресу, если указан
        if mac:
            mac_upper = mac.upper()
            self._devices_by_mac[mac_upper] = device
            _LOGGER.info("Добавлено устройство: %s (%s) с MAC %s", name, device_id, mac)
        else:
            _LOGGER.info("Добавлено устройство: %s (%s)", name, device_id)
        
        _LOGGER.debug(
            "Инициализированы значения по умолчанию для select'ов устройства %s: ctype0=-1, ctype1=-1, data_type0=6, data_type1=6, f0=1, f1=1",
            device_id
        )
        
        return True

    def remove_device(self, device_id: str) -> bool:
        """Удаление устройства.
        
        Args:
            device_id: ID устройства для удаления
            
        Returns:
            True если устройство успешно удалено, False если не найдено
        """
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
        """Получение устройства по ID.
        
        Args:
            device_id: ID устройства
            
        Returns:
            Объект WateriusDevice или None если не найдено
        """
        return self._devices.get(device_id)

    def get_device_by_mac(self, mac: str) -> WateriusDevice | None:
        """Получение устройства по MAC адресу.
        
        Args:
            mac: MAC адрес устройства (в верхнем регистре)
            
        Returns:
            Объект WateriusDevice или None если не найдено
        """
        mac_upper = mac.upper()
        return self._devices_by_mac.get(mac_upper)

    def get_device_by_serial(self, serial: str) -> WateriusDevice | None:
        """Получение устройства по серийному номеру.
        
        Args:
            serial: Серийный номер устройства (key)
            
        Returns:
            Объект WateriusDevice или None если не найдено
        """
        # Серийный номер хранится в device.data["key"]
        # Перебираем все устройства и ищем по серийному номеру
        for device in self._devices.values():
            if device.data and device.data.get("key") == serial:
                return device
        return None

    def get_all_devices(self) -> dict[str, WateriusDevice]:
        """Получение всех устройств."""
        return self._devices.copy()

    def update_device_data(self, device_id: str, data: dict[str, Any]) -> bool:
        """Обновление данных устройства.
        
        Args:
            device_id: ID устройства
            data: Новые данные от устройства
            
        Returns:
            True если данные успешно обновлены, False если устройство не найдено
        """
        if device_id not in self._devices:
            _LOGGER.warning("Устройство с ID %s не найдено", device_id)
            return False

        device = self._devices[device_id]
        
        # Объединяем данные вместо полной перезаписи
        # Это сохраняет значения по умолчанию и предыдущие данные,
        # которые не присутствуют в новом обновлении
        if device.data is None:
            device.data = {}
        
        # Определяем, это ПЕРВОЕ получение данных от устройства или нет
        is_first_update = not device.data or device.last_update_time is None
        
        # ✅ НОВАЯ АРХИТЕКТУРА: device.data ВСЕГДА обновляется от устройства!
        # Фильтрация конфигурационных ключей НЕ нужна, потому что:
        # - Select/Number entities хранят своё состояние внутри (желаемые значения)
        # - device.data хранит текущее состояние устройства (реальные значения)
        # - Это позволяет видеть разницу между желаемым и текущим!
        device.data.update(data)
        
        # last_update_time обновляется при получении данных от устройства
        if "timestamp" in data:
            device.last_update_time = datetime.now()

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

        if is_first_update:
            _LOGGER.info(
                "🆕 Первое получение данных от устройства %s: принято %d ключей",
                device_id, len(data)
            )
        else:
            _LOGGER.debug(
                "Обновлены данные устройства %s: %d ключей", 
                device_id, len(data)
            )
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

