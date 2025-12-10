"""Sensor platform для интеграции Waterius."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume, UnitOfElectricPotential, PERCENTAGE, UnitOfInformation, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.entity_registry as er

from .const import DOMAIN
from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)

# Типы данных каналов (соответствуют DATA_TYPE_OPTIONS из select.py)
DATA_TYPE_OPTIONS = [
    "WATER_COLD",      # 0
    "WATER_HOT",       # 1
    "ELECTRO",         # 2
    "GAS",             # 3
    "HEAT_GCAL",       # 4
    "PORTABLE_WATER",  # 5
    "OTHER",           # 6
    "HEAT_KWT",        # 7
]

# Все сенсоры (основные и диагностические)
# Порядок элементов определяет порядок отображения в интерфейсе Home Assistant
SENSOR_DESCRIPTIONS = [
    # ========== ОСНОВНЫЕ СЕНСОРЫ ==========
    SensorEntityDescription(
        key="ch0",
        translation_key="ch0",
        # native_unit_of_measurement и device_class определяются динамически
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),
    SensorEntityDescription(
        key="ch1",
        translation_key="ch1",
        # native_unit_of_measurement и device_class определяются динамически
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),
    SensorEntityDescription(
        key="delta0",
        translation_key="delta0",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="delta1",
        translation_key="delta1",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    
    # ========== СЕНСОРЫ КАНАЛОВ ==========
    SensorEntityDescription(
        key="ch0_start",
        translation_key="ch0_start",
        # native_unit_of_measurement и device_class определяются динамически
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water",
    ),
    SensorEntityDescription(
        key="ch1_start",
        translation_key="ch1_start",
        # native_unit_of_measurement и device_class определяются динамически
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water",
    ),
    SensorEntityDescription(
        key="imp0",
        translation_key="imp0",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:pulse",
    ),
    SensorEntityDescription(
        key="imp1",
        translation_key="imp1",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:pulse",
    ),
    SensorEntityDescription(
        key="adc0",
        translation_key="adc0",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gauge",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="adc1",
        translation_key="adc1",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gauge",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="ctype0",
        translation_key="ctype0",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water-pump",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="ctype1",
        translation_key="ctype1",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water-pump",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="cname0",
        translation_key="cname0",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:label",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="cname1",
        translation_key="cname1",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:label",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="data_type0",
        translation_key="data_type0",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:database",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="data_type1",
        translation_key="data_type1",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:database",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="f0",
        translation_key="f0",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calculator",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="f1",
        translation_key="f1",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calculator",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="serial0",
        translation_key="serial0",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
    ),
    SensorEntityDescription(
        key="serial1",
        translation_key="serial1",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
    ),
    
    # ========== ЭНЕРГИЯ/БАТАРЕЯ ==========
    SensorEntityDescription(
        key="battery",
        translation_key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
    ),
    SensorEntityDescription(
        key="voltage_low",
        translation_key="voltage_low",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery-alert",
    ),
    SensorEntityDescription(
        key="voltage_diff",
        translation_key="voltage_diff",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:lightning-bolt",
        suggested_display_precision=3,
    ),
    
    # ========== СЕТЬ ==========
    SensorEntityDescription(
        key="channel",
        translation_key="channel",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="wifi_phy_mode",
        translation_key="wifi_phy_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
    ),
    SensorEntityDescription(
        key="wifi_phy_mode_s",
        translation_key="wifi_phy_mode_s",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
    ),
    SensorEntityDescription(
        key="router_mac",
        translation_key="router_mac",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:router-network",
    ),
    SensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:signal",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="ip",
        translation_key="ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:ip-network",
    ),
    SensorEntityDescription(
        key="dhcp",
        translation_key="dhcp",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:router-network",
    ),
    SensorEntityDescription(
        key="mac",
        translation_key="mac",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:network",
    ),
    
    # ========== СИСТЕМА/УСТРОЙСТВО ==========
    SensorEntityDescription(
        key="version",
        translation_key="version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:integrated-circuit-chip",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="version_esp",
        translation_key="version_esp",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
    ),
    SensorEntityDescription(
        key="esp_id",
        translation_key="esp_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="flash_id",
        translation_key="flash_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="freemem",
        translation_key="freemem",
        native_unit_of_measurement="B",  # Используем строку 'B' для стабильности единицы измерения
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:memory",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="email",
        translation_key="email",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:email",
    ),
    SensorEntityDescription(
        key="timestamp",
        translation_key="timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-time-four",
    ),
    
    # ========== ВРЕМЯ/ТАЙМЕРЫ ==========
    SensorEntityDescription(
        key="waketime",
        translation_key="waketime",
        native_unit_of_measurement="ms",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-start",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="setuptime",
        translation_key="setuptime",
        native_unit_of_measurement="ms",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cog-clockwise",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="period_min",
        translation_key="period_min",
        native_unit_of_measurement="min",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="period_min_tuned",
        translation_key="period_min_tuned",
        native_unit_of_measurement="min",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer",
        suggested_display_precision=0,
    ),
    
    # ========== СОСТОЯНИЕ/СОБЫТИЯ ==========
    SensorEntityDescription(
        key="boot",
        translation_key="boot",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:restart",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="resets",
        translation_key="resets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:restart",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="mode",
        translation_key="mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:toggle-switch",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="setup_started",
        translation_key="setup_started",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:play-circle",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="setup_finished",
        translation_key="setup_finished",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:check",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="ntp_errors",
        translation_key="ntp_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-alert",
        suggested_display_precision=0,
    ),
    
    # ========== ПРОТОКОЛЫ ==========
    SensorEntityDescription(
        key="mqtt",
        translation_key="mqtt",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:home-assistant",
    ),
    SensorEntityDescription(
        key="ha",
        translation_key="ha",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:home-assistant",
    ),
    SensorEntityDescription(
        key="http",
        translation_key="http",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:web",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка sensor платформы."""
    device_manager: DeviceManager = hass.data[DOMAIN][entry.entry_id]["device_manager"]
    
    # Сохраняем callback для добавления новых entities
    hass.data[DOMAIN][entry.entry_id]["sensor_add_entities"] = async_add_entities
    
    entities = []
    
    # Создаем entities для каждого устройства
    for device in device_manager.get_all_devices().values():
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                WateriusSensor(
                    device_manager,
                    device.device_id,
                    device.name,
                    device.mac,
                    description,
                    entry.entry_id,
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
        
        # Создаем entities для нового устройства
        new_entities = []
        for description in SENSOR_DESCRIPTIONS:
            new_entities.append(
                WateriusSensor(
                    device_manager,
                    device_id,
                    device_name,
                    device_mac,
                    description,
                    entry.entry_id,
                )
            )
        
        async_add_entities(new_entities, update_before_add=True)
        _LOGGER.info("Созданы sensor entities для устройства %s", device_name)
    
    hass.bus.async_listen("waterius_device_added", handle_device_added)


class WateriusSensor(SensorEntity, RestoreEntity):
    """Представление sensor для устройства Waterius."""

    def __init__(
        self,
        device_manager: DeviceManager,
        device_id: str,
        device_name: str,
        device_mac: str | None,
        description: SensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Инициализация sensor."""
        self._device_manager = device_manager
        self._device_id = device_id
        self._device_name = device_name
        self._device_mac = device_mac
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_has_entity_name = True
        self._entry_id = entry_id
        self._unsub_update = None
        self._attr_native_value = None  # Для сохранения состояния
        # Сохраняем предыдущие значения data_type для отслеживания изменений
        self._prev_data_type_0 = None
        self._prev_data_type_1 = None

    async def async_added_to_hass(self) -> None:
        """Вызывается при добавлении entity в hass."""
        await super().async_added_to_hass()
        
        # Список сенсоров, которые должны быть скрыты по умолчанию
        hidden_sensors = {
            "ctype0",  # channel_0_type
            "ctype1",  # channel_1_type
            "data_type0",  # channel_0_data_type
            "data_type1",  # channel_1_data_type
            "setuptime",  # setup_time
            "version",  # version
            "version_esp",  # esp_version
            "boot",  # boots
            "imp0",  # channel_0_impulses
            "imp1",  # channel_1_impulses
            "setup_finished",  # setups_finished
            "setup_started",  # setups_started
            "mode",  # mode
            "freemem",  # free_memory
            "email",  # email
            "ha",  # home_assistant
            "http",  # http
            "ip",  # ip_address
            "dhcp",  # dhcp
            "adc0",  # channel_0_adc
            "adc1",  # channel_1_adc
            "period_min",  # period
            "period_min_tuned",  # period_tuned
            "cname0",  # channel_0_name
            "cname1",  # channel_1_name
            "f0",  # channel_0_conversion_factor
            "f1",  # channel_1_conversion_factor
            "ch0_start",  # channel_0_start_value
            "ch1_start",  # channel_1_start_value
            "mqtt",  # mqtt
            "wifi_phy_mode",  # wifi_phy_mode
            "esp_id",  # esp_id
            "flash_id",  # flash_id
            "wifi_phy_mode_s",  # wifi_phy_mode_string
            "delta0",  # delta_0
            "delta1",  # delta_1
        }
        
        # Скрываем сенсоры по умолчанию, если они в списке
        # Используем отложенную задачу, чтобы entity успел зарегистрироваться
        if self.entity_description.key in hidden_sensors:
            async def hide_entity():
                """Скрытие entity после регистрации."""
                await asyncio.sleep(0.1)  # Небольшая задержка для регистрации entity
                registry = er.async_get(self.hass)
                entity_id = registry.async_get_entity_id("sensor", DOMAIN, self._attr_unique_id)
                if entity_id:
                    entry = registry.async_get(entity_id)
                    if entry and entry.disabled_by is None:
                        # Скрываем entity только если она еще не скрыта
                        registry.async_update_entity(
                            entity_id,
                            disabled_by=er.RegistryEntryDisabler.INTEGRATION
                        )
                        _LOGGER.debug("Скрыт сенсор %s по умолчанию", self.entity_description.key)
            
            self.hass.async_create_task(hide_entity())
        
        # Восстанавливаем последнее сохраненное состояние
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable", None):
                try:
                    # Восстанавливаем значение из сохраненного состояния
                    # Используем native_value из атрибутов, если доступен (предпочтительно)
                    if hasattr(last_state, "attributes") and "native_value" in last_state.attributes:
                        self._attr_native_value = last_state.attributes["native_value"]
                    else:
                        # Иначе пытаемся преобразовать state (строка)
                        state_value = last_state.state
                        # Обрабатываем значение так же, как при получении новых данных
                        if state_value:
                            self._attr_native_value = self._process_value(state_value)
                except (ValueError, TypeError) as e:
                    _LOGGER.debug("Не удалось восстановить состояние для %s: %s", self.entity_id, e)
        
        # Инициализируем предыдущие значения data_type из device.data
        device = self._device_manager.get_device(self._device_id)
        if device and device.data:
            if self.entity_description.key in ("ch0", "ch0_start"):
                self._prev_data_type_0 = device.data.get("data_type0")
            elif self.entity_description.key in ("ch1", "ch1_start"):
                self._prev_data_type_1 = device.data.get("data_type1")
        
        # Подписываемся на события обновления устройства
        @callback
        def handle_device_update(event: Event) -> None:
            """Обработка обновления данных устройства."""
            if event.data.get("device_id") == self._device_id:
                device = self._device_manager.get_device(self._device_id)
                
                # Проверяем, изменился ли тип данных для каналов
                data_type_changed = False
                if device and device.data:
                    # Проверяем data_type0 для канала 0
                    if self.entity_description.key in ("ch0", "ch0_start"):
                        current_data_type_0 = device.data.get("data_type0")
                        if current_data_type_0 != self._prev_data_type_0:
                            data_type_changed = True
                            self._prev_data_type_0 = current_data_type_0
                    
                    # Проверяем data_type1 для канала 1
                    elif self.entity_description.key in ("ch1", "ch1_start"):
                        current_data_type_1 = device.data.get("data_type1")
                        if current_data_type_1 != self._prev_data_type_1:
                            data_type_changed = True
                            self._prev_data_type_1 = current_data_type_1
                
                # Обновляем информацию об устройстве в device registry
                self._update_device_info()
                
                # Если изменился тип данных, принудительно обновляем состояние
                # чтобы пересчитать native_unit_of_measurement и device_class
                if data_type_changed:
                    # Используем async_write_ha_state для обновления состояния
                    # Свойства native_unit_of_measurement и device_class вычисляются динамически
                    # через @property, поэтому они пересчитаются при следующем обращении
                    self.async_write_ha_state()
                    # Также обновляем entity registry, чтобы Home Assistant знал об изменении
                    registry = er.async_get(self.hass)
                    entity_id = registry.async_get_entity_id("sensor", DOMAIN, self._attr_unique_id)
                    if entity_id:
                        # Обновляем entity, что заставит Home Assistant пересчитать свойства
                        registry.async_update_entity(entity_id)
                else:
                    # Обычное обновление состояния
                    self.async_write_ha_state()
        
        self._unsub_update = self.hass.bus.async_listen(
            "waterius_device_update", handle_device_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Вызывается при удалении entity из hass."""
        if self._unsub_update:
            self._unsub_update()
        await super().async_will_remove_from_hass()

    @property
    def device_info(self) -> DeviceInfo:
        """Информация об устройстве."""
        identifiers = {(DOMAIN, self._device_id)}
        if self._device_mac:
            identifiers.add((DOMAIN, self._device_mac))
        
        # Получаем данные устройства для извлечения дополнительной информации
        device = self._device_manager.get_device(self._device_id)
        sw_version = None
        model = "Classic"  # Модель всегда Classic
        hw_version = "1.0.0"  # Версия аппаратного обеспечения всегда 1.0.0
        serial_number = None
        configuration_url = None
        
        if device and device.data:
            # Формируем версию программного обеспечения из version_esp и version
            # Формат: version_esp.version (сначала version_esp, потом точка, потом version)
            version_esp = device.data.get("version_esp")
            version = device.data.get("version")
            if version_esp is not None and version is not None:
                sw_version = f"{version_esp}.{version}"
            elif version_esp is not None:
                sw_version = str(version_esp)
            elif version is not None:
                sw_version = str(version)
            
            # Получаем серийный номер из поля key
            serial_number = device.data.get("key")
            
            # Получаем IP адрес для configuration_url
            ip_address = device.data.get("ip")
            if ip_address:
                configuration_url = f"http://{ip_address}"
        
        return DeviceInfo(
            identifiers=identifiers,
            name=self._device_name,
            manufacturer="Waterius",
            model=model,
            hw_version=hw_version,
            sw_version=sw_version,
            serial_number=serial_number,
            configuration_url=configuration_url,
        )

    @property
    def icon(self) -> str | None:
        """Иконка сенсора."""
        if self.entity_description.icon:
            return self.entity_description.icon
        return None

    def _get_data_type_string(self, channel: int) -> str | None:
        """Получение строки типа данных для канала из device.data."""
        device = self._device_manager.get_device(self._device_id)
        if not device or not device.data:
            return None
        
        # Получаем числовое значение типа данных
        data_type_key = f"data_type{channel}"
        data_type_value = device.data.get(data_type_key)
        
        if data_type_value is None:
            return None
        
        # Преобразуем число в строку
        try:
            type_int = int(float(data_type_value))
            if 0 <= type_int < len(DATA_TYPE_OPTIONS):
                return DATA_TYPE_OPTIONS[type_int]
            else:
                return "OTHER"
        except (ValueError, TypeError):
            return None

    def _get_unit_and_device_class(self, data_type: str | None) -> tuple[str | None, SensorDeviceClass | None]:
        """Определение единиц измерения и device_class на основе типа данных."""
        if not data_type:
            # Значения по умолчанию (вода)
            return UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER
        
        # Вода: холодная, горячая, питьевая
        if data_type in ("WATER_COLD", "WATER_HOT", "PORTABLE_WATER"):
            return UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER
        
        # Газ
        if data_type == "GAS":
            return UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER
        
        # Электроэнергия
        if data_type == "ELECTRO":
            return UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY
        
        # Тепло (Гкал и кВт)
        if data_type in ("HEAT_GCAL", "HEAT_KWT"):
            return UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY
        
        # Другие типы - используем значения по умолчанию
        return UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Единица измерения сенсора (динамически определяется для ch0, ch1, ch0_start, ch1_start)."""
        # Для сенсоров каналов определяем единицы измерения динамически
        if self.entity_description.key in ("ch0", "ch0_start"):
            data_type = self._get_data_type_string(0)
            unit, _ = self._get_unit_and_device_class(data_type)
            return unit
        elif self.entity_description.key in ("ch1", "ch1_start"):
            data_type = self._get_data_type_string(1)
            unit, _ = self._get_unit_and_device_class(data_type)
            return unit
        
        # Для остальных сенсоров используем значение из описания
        return self.entity_description.native_unit_of_measurement

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Класс устройства сенсора (динамически определяется для ch0, ch1, ch0_start, ch1_start)."""
        # Для сенсоров каналов определяем device_class динамически
        if self.entity_description.key in ("ch0", "ch0_start"):
            data_type = self._get_data_type_string(0)
            _, device_class = self._get_unit_and_device_class(data_type)
            return device_class
        elif self.entity_description.key in ("ch1", "ch1_start"):
            data_type = self._get_data_type_string(1)
            _, device_class = self._get_unit_and_device_class(data_type)
            return device_class
        
        # Для остальных сенсоров используем значение из описания
        return self.entity_description.device_class

    @property
    def native_value(self) -> float | int | str | bool | datetime | None:
        """Текущее значение sensor."""
        device = self._device_manager.get_device(self._device_id)
        
        # Если есть данные устройства, используем их
        if device and device.data:
            value = device.data.get(self.entity_description.key)
            if value is not None:
                # Обрабатываем значение
                processed_value = self._process_value(value)
                # Сохраняем в атрибут для восстановления состояния
                self._attr_native_value = processed_value
                return processed_value
        
        # Если данных нет, возвращаем сохраненное значение (для восстановления состояния)
        return self._attr_native_value
    
    def _process_value(self, value: Any) -> float | int | str | bool | datetime:
        """Обработка значения сенсора."""
        # Для булевых значений возвращаем как есть
        if isinstance(value, bool):
            return value
        
        # Для timestamp сенсоров преобразуем строку в datetime
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            # Если значение уже datetime, возвращаем как есть
            if isinstance(value, datetime):
                return value
            
            # Если значение строка, преобразуем в datetime
            if not isinstance(value, str):
                return value
            
            try:
                
                # Нормализуем формат timezone offset: +0000 -> +00:00
                # Формат: 2025-11-28T19:09:36+0000 -> 2025-11-28T19:09:36+00:00
                if len(value) == 24 and value[19] in ["+", "-"] and value[23].isdigit():
                    # Формат: YYYY-MM-DDTHH:MM:SS+HHMM (без двоеточия в offset)
                    value = value[:19] + value[19:22] + ":" + value[22:]
                
                # Заменяем Z на +00:00 для UTC
                if value.endswith("Z"):
                    value = value.replace("Z", "+00:00")
                
                # Парсим ISO 8601 формат
                return datetime.fromisoformat(value)
            except (ValueError, AttributeError) as e:
                _LOGGER.warning(
                    "Не удалось преобразовать timestamp '%s' в datetime: %s", value, e
                )
                # Возвращаем исходную строку, если не удалось преобразовать
                return value
        
        # Для остальных строк возвращаем как есть
        if isinstance(value, str):
            return value
        
        # Список ключей, которые должны быть целыми числами
        integer_keys = {
            "version", "boot", "channel", 
            "setup_finished", "setup_started", "ntp_errors", 
            "resets", "mode", "esp_id", "flash_id", "freemem",
            "period_min_tuned", "period_min", "waketime", "setuptime", "rssi",
            "imp0", "imp1", "adc0", "adc1", "ctype0", "ctype1", 
            "cname0", "cname1", "data_type0", "data_type1", "f0", "f1"
        }
        
        # Для числовых значений
        try:
            if self.entity_description.key in integer_keys:
                # Для целочисленных сенсоров возвращаем int
                return int(float(value))
            else:
                # Для остальных возвращаем float
                return float(value)
        except (ValueError, TypeError):
            return str(value) if value is not None else None

    @property
    def available(self) -> bool:
        """Доступность sensor."""
        device = self._device_manager.get_device(self._device_id)
        # Устройство доступно, если оно существует в менеджере
        # Данные могут прийти позже, поэтому не требуем их наличия для доступности
        return device is not None

    @callback
    def _update_device_info(self) -> None:
        """Обновление информации об устройстве в device registry."""
        device = self._device_manager.get_device(self._device_id)
        if not device:
            return
        
        # Если данных еще нет, не обновляем device registry
        if not device.data:
            return
        
        try:
            # Получаем device registry
            dev_reg = dr.async_get(self.hass)
            
            # Находим устройство по идентификаторам
            identifiers = {(DOMAIN, self._device_id)}
            if self._device_mac:
                identifiers.add((DOMAIN, self._device_mac))
            
            device_entry = dev_reg.async_get_device(identifiers=identifiers)
            if not device_entry:
                return
            
            # Формируем версию программного обеспечения
            # Формат: version_esp.version (сначала version_esp, потом точка, потом version)
            version_esp = device.data.get("version_esp")
            version = device.data.get("version")
            sw_version = None
            if version_esp is not None and version is not None:
                sw_version = f"{version_esp}.{version}"
            elif version_esp is not None:
                sw_version = str(version_esp)
            elif version is not None:
                sw_version = str(version)
            
            # Получаем серийный номер из поля key
            serial_number = device.data.get("key")
            
            # Получаем IP адрес для configuration_url
            ip_address = device.data.get("ip")
            configuration_url = None
            if ip_address:
                configuration_url = f"http://{ip_address}"
            
            # Версия аппаратного обеспечения всегда 1.0.0
            hw_version = "1.0.0"
            
            # Обновляем информацию об устройстве
            dev_reg.async_update_device(
                device_entry.id,
                hw_version=hw_version,
                sw_version=sw_version,
                serial_number=serial_number,
                configuration_url=configuration_url,
            )
        except Exception as e:
            _LOGGER.warning("Ошибка при обновлении информации об устройстве: %s", e)

