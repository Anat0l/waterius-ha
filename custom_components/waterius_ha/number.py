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
from .entity import WateriusEntity
from .helpers import get_device_info, setup_device_added_listener
from . import WateriusConfigEntry

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
    entry: WateriusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка number платформы."""
    if entry.runtime_data is None:
        _LOGGER.error("Runtime data не инициализирована для entry %s", entry.entry_id)
        return

    device_manager: DeviceManager = entry.runtime_data.device_manager

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
    setup_device_added_listener(
        hass,
        entry.entry_id,
        device_manager,
        async_add_entities,
        lambda dm, did, dn, dmac, desc: WateriusNumber(dm, did, dn, dmac, desc, entry),
        NUMBER_DESCRIPTIONS,
        "number",
    )


class WateriusNumber(WateriusEntity, NumberEntity, RestoreEntity):
    """Представление number для интервала обновления устройства Waterius.
    
    Использует push-based модель: устройства отправляют данные на веб-сервер,
    entities обновляются через события. Не требует ограничения параллельных
    обновлений, т.к. нет активных сетевых запросов к устройствам.
    """
    
    PARALLEL_UPDATES = 0  # Нет ограничений для push-based модели

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
        super().__init__(device_manager, device_id, device_name, device_mac)
        self._base_description = description
        self._attr_unique_id = f"{device_id}_{description.key}_config"
        self._attr_has_entity_name = True
        self._entry = entry
        self._attr_native_value: float | None = None
        self._unsub_update = None  # Подписка на события обновления устройства

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
        
        # ✅ НОВАЯ АРХИТЕКТУРА: Number НЕ обновляется от устройства!
        # Number хранит ЖЕЛАЕМОЕ значение (что хочет пользователь)
        # Sensor хранит ТЕКУЩЕЕ значение (что реально на устройстве)
        # Number обновляется ТОЛЬКО при изменении пользователем!
        # Подписка на события НЕ нужна.

    def _load_from_sensor(self) -> None:
        """Загрузка значения из сенсора устройства."""
        device = self._device_manager.get_device(self._device_id)
        if not device or not device.data:
            return
        
        # Читаем значение из сенсора period_min
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
        
        # ✅ НОВАЯ АРХИТЕКТУРА: Number НЕ обновляет device.data!
        # Number хранит ЖЕЛАЕМОЕ значение (что хочет пользователь)
        # device.data хранит ТЕКУЩЕЕ значение (что реально на устройстве)
        # Это позволяет видеть разницу!
        
        # Обновляем текущее значение (хранится в Number entity)
        self._attr_native_value = int(value)
        self.async_write_ha_state()
        
        _LOGGER.info(
            "👤 ПОЛЬЗОВАТЕЛЬ изменил интервал обновления для устройства %s: %d мин",
            self._device_name,
            int(value)
        )

