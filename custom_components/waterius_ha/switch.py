"""Switch платформа для интеграции Waterius."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device_manager import DeviceManager
from .entity import WateriusEntity
from .helpers import get_device_info, setup_device_added_listener
from . import WateriusConfigEntry

_LOGGER = logging.getLogger(__name__)

# Описание switch entity
SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="send_settings",
    translation_key="send_settings",
    entity_category=EntityCategory.CONFIG,
    icon="mdi:cloud-upload",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WateriusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка switch entities из config entry."""
    device_manager = entry.runtime_data.device_manager
    
    # Создаем switch для каждого устройства
    switches = []
    for device_id, device in device_manager.get_all_devices().items():
        switches.append(
            WateriusSendSettingsSwitch(
                device_manager,
                device_id,
                device.name,
                device.mac,
                entry,
            )
        )
    
    async_add_entities(switches)
    
    # Подписываемся на события добавления новых устройств
    setup_device_added_listener(
        hass,
        entry.entry_id,
        device_manager,
        async_add_entities,
        lambda dm, did, dn, dmac, desc: WateriusSendSettingsSwitch(dm, did, dn, dmac, entry),
        [SWITCH_DESCRIPTION],
        "switch",
    )


class WateriusSendSettingsSwitch(WateriusEntity, SwitchEntity):
    """Switch для отправки настроек устройству Waterius."""
    
    entity_description: SwitchEntityDescription
    
    def __init__(
        self,
        device_manager: DeviceManager,
        device_id: str,
        device_name: str,
        device_mac: str | None,
        entry: WateriusConfigEntry,
    ) -> None:
        """Инициализация switch."""
        super().__init__(device_manager, device_id, device_name, device_mac)
        self.entity_description = SWITCH_DESCRIPTION
        self._entry = entry
        self._attr_is_on = False
        
        # Уникальный ID для entity
        self._attr_unique_id = f"{device_id}_{SWITCH_DESCRIPTION.key}"
        self._attr_name = f"{device_name} Отправить настройки"
    
    @property
    def is_on(self) -> bool:
        """Возвращает состояние переключателя."""
        return self._attr_is_on
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Включение переключателя (пометить для отправки настроек)."""
        self._attr_is_on = True
        self.async_write_ha_state()
        
        _LOGGER.info(
            "Переключатель отправки настроек включен для устройства %s (%s)",
            self._device_name,
            self._device_id
        )
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Выключение переключателя."""
        self._attr_is_on = False
        self.async_write_ha_state()
        
        _LOGGER.debug(
            "Переключатель отправки настроек выключен для устройства %s (%s)",
            self._device_name,
            self._device_id
        )
    
    def should_send_settings(self) -> bool:
        """Проверка, нужно ли отправлять настройки."""
        return self._attr_is_on
    
    async def mark_settings_sent(self) -> None:
        """Пометить настройки как отправленные (выключить переключатель)."""
        await self.async_turn_off()

