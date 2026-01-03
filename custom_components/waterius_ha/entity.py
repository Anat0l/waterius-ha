"""Базовый класс для entities интеграции Waterius."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo, Entity

from .device_manager import DeviceManager
from .helpers import get_device_info


class WateriusEntity(Entity):
    """Базовый класс для всех entities интеграции Waterius."""

    def __init__(
        self,
        device_manager: DeviceManager,
        device_id: str,
        device_name: str,
        device_mac: str | None,
    ) -> None:
        """Инициализация базового entity.
        
        Args:
            device_manager: Менеджер устройств
            device_id: ID устройства
            device_name: Имя устройства
            device_mac: MAC адрес устройства
        """
        self._device_manager = device_manager
        self._device_id = device_id
        self._device_name = device_name
        self._device_mac = device_mac
        self._unsub_update = None

    @property
    def device_info(self) -> DeviceInfo:
        """Информация об устройстве."""
        return get_device_info(
            self._device_manager,
            self._device_id,
            self._device_name,
            self._device_mac,
        )

    @property
    def available(self) -> bool:
        """Доступность entity."""
        device = self._device_manager.get_device(self._device_id)
        # Устройство доступно, если оно существует в менеджере
        # Данные могут прийти позже, поэтому не требуем их наличия для доступности
        return device is not None

    async def async_will_remove_from_hass(self) -> None:
        """Вызывается при удалении entity из hass.
        
        Отменяет все активные подписки на события для предотвращения утечек памяти.
        """
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        # Отменяем дополнительные подписки, если они есть
        if hasattr(self, "_unsub_entity_registry") and self._unsub_entity_registry:
            self._unsub_entity_registry()
            self._unsub_entity_registry = None
        if hasattr(self, "_unsub_entity_registry_hide") and self._unsub_entity_registry_hide:
            self._unsub_entity_registry_hide()
            self._unsub_entity_registry_hide = None
        await super().async_will_remove_from_hass()

