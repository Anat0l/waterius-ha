"""Number platform для интеграции Waterius."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CONF_DEVICES, CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_DEVICE_MAC
from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)

# Описания number entities
NUMBER_DESCRIPTIONS = [
    NumberEntityDescription(
        key="period_min",
        translation_key="period_min_config",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:timer",
        native_min_value=1,
        native_max_value=1440,
        native_step=1,
        mode=NumberMode.BOX,
        native_unit_of_measurement="min",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка number платформы."""
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        return

    entry_data = hass.data[DOMAIN][entry.entry_id]
    device_manager: DeviceManager = entry_data.get("device_manager")

    if not device_manager:
        return

    # Создаем number entities для всех устройств
    entities = []
    devices = entry.data.get(CONF_DEVICES, [])
    
    for device_config in devices:
        device_id = device_config.get(CONF_DEVICE_ID)
        device_name = device_config.get(CONF_DEVICE_NAME)
        device_mac = device_config.get(CONF_DEVICE_MAC)
        
        if not device_id or not device_name:
            continue
        
        # Создаем number entities для каждого устройства
        for description in NUMBER_DESCRIPTIONS:
            entities.append(
                WateriusNumber(
                    device_manager,
                    device_id,
                    device_name,
                    device_mac,
                    description,
                    entry,
                )
            )
    
    async_add_entities(entities, update_before_add=True)
    
    # Подписываемся на события добавления новых устройств
    @callback
    def handle_device_added(event: Event) -> None:
        """Обработка добавления нового устройства."""
        if event.data.get("entry_id") != entry.entry_id:
            return
        
        device_id = event.data.get("device_id")
        device_name = event.data.get("device_name")
        device_mac = event.data.get("device_mac")
        
        if not device_id or not device_name:
            return
        
        # Создаем number entities для нового устройства
        new_entities = []
        for description in NUMBER_DESCRIPTIONS:
            new_entities.append(
                WateriusNumber(
                    device_manager,
                    device_id,
                    device_name,
                    device_mac,
                    description,
                    entry,
                )
            )
        
        async_add_entities(new_entities, update_before_add=True)
        _LOGGER.info("Созданы number entities для устройства %s", device_name)
    
    hass.bus.async_listen("waterius_device_added", handle_device_added)


class WateriusNumber(NumberEntity, RestoreEntity):
    """Представление number для интервала обновления устройства Waterius."""

    def __init__(
        self,
        device_manager: DeviceManager,
        device_id: str,
        device_name: str,
        device_mac: str | None,
        description: NumberEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Инициализация number."""
        self._device_manager = device_manager
        self._device_id = device_id
        self._device_name = device_name
        self._device_mac = device_mac
        self._base_description = description
        self._attr_unique_id = f"{device_id}_{description.key}_config"
        self._attr_has_entity_name = True
        self._entry = entry
        self._attr_native_value = None

    @property
    def device_info(self) -> DeviceInfo:
        """Информация об устройстве."""
        identifiers = {(DOMAIN, self._device_id)}
        if self._device_mac:
            identifiers.add((DOMAIN, self._device_mac))
        
        return DeviceInfo(
            identifiers=identifiers,
            name=self._device_name,
            manufacturer="Waterius",
            model="Classic",
            hw_version="1.0.0",
        )
    
    @property
    def entity_description(self) -> NumberEntityDescription:
        """Описание entity."""
        return self._base_description

    async def async_added_to_hass(self) -> None:
        """Вызывается при добавлении entity в hass."""
        await super().async_added_to_hass()
        
        # Восстанавливаем последнее сохраненное состояние
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable", None):
                try:
                    self._attr_native_value = float(last_state.state)
                except (ValueError, TypeError):
                    pass
        
        # Загружаем значение из сенсора
        self._load_from_sensor()
        
        # Подписываемся на события обновления устройства
        @callback
        def handle_device_update(event: Event) -> None:
            """Обработка обновления данных устройства."""
            if event.data.get("device_id") == self._device_id:
                self._load_from_sensor()
                self.async_write_ha_state()
        
        self.hass.bus.async_listen("waterius_device_update", handle_device_update)

    def _load_from_sensor(self) -> None:
        """Загрузка значения из сенсора устройства."""
        device = self._device_manager.get_device(self._device_id)
        if not device or not device.data:
            return
        
        # Читаем значение из сенсора period_min
        if self.entity_description.key == "period_min":
            period_min_value = device.data.get("period_min")
            if period_min_value is not None:
                try:
                    self._attr_native_value = int(float(period_min_value))
                except (ValueError, TypeError):
                    pass

    async def async_set_native_value(self, value: float) -> None:
        """Обработка установки значения."""
        # Получаем устройство
        device = self._device_manager.get_device(self._device_id)
        if not device:
            _LOGGER.warning("Устройство %s не найдено", self._device_id)
            return
        
        # Обновляем данные устройства
        if device.data is None:
            device.data = {}
        
        # Обновляем значение period_min в данных устройства
        if self.entity_description.key == "period_min":
            device.data["period_min"] = int(value)
        
        # Обновляем данные через device_manager, чтобы сенсор автоматически обновился
        self._device_manager.update_device_data(self._device_id, device.data)
        
        # Обновляем текущее значение
        self._attr_native_value = int(value)
        self.async_write_ha_state()
        
        _LOGGER.info(
            "Обновлен интервал обновления для устройства %s: %d мин",
            self._device_name,
            int(value)
        )

