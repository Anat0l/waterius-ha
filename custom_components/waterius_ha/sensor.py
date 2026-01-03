"""Sensor platform для интеграции Waterius."""
from __future__ import annotations

import logging
import socket
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfVolume,
    UnitOfElectricPotential,
    PERCENTAGE,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.entity_registry as er

from .const import DOMAIN, DEVICE_HW_VERSION, DEVICE_MANUFACTURER, COUNTER_NAME_OPTIONS
from .device_manager import DeviceManager
from .entity import WateriusEntity
from .helpers import (
    get_device_info,
    get_device_identifiers,
    get_software_version,
    get_configuration_url,
    setup_device_added_listener,
)
from .translations import load_translations_from_json
from . import WateriusConfigEntry

_LOGGER = logging.getLogger(__name__)

# Маппинг типов данных на единицы измерения и device_class для оптимизации
_DATA_TYPE_MAPPING: dict[str, tuple[str | None, SensorDeviceClass | None]] = {
    "WATER_COLD": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER),
    "WATER_HOT": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER),
    "PORTABLE_WATER": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER),
    "GAS": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.GAS),
    "ELECTRO": (UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY),
    "HEAT_GCAL": ("Gcal", None),  # Пользовательская единица без device_class
    "HEAT_KWT": (UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY),
    "OTHER": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER),
}

# Список сенсоров, которые должны быть скрыты по умолчанию
HIDDEN_SENSORS: frozenset[str] = frozenset({
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
    "company",  # company
    "place",  # place
})

# Список ключей сенсоров, которые должны быть целыми числами
INTEGER_SENSOR_KEYS: frozenset[str] = frozenset({
    "version", "boot", "channel", 
    "setup_finished", "setup_started", "ntp_errors", 
    "resets", "mode", "esp_id", "flash_id", "freemem",
    "period_min_tuned", "period_min", "waketime", "setuptime", "rssi",
    "imp0", "imp1", "adc0", "adc1", "ctype0", "ctype1", 
    "cname0", "cname1", "data_type0", "data_type1", "f0", "f1"
})

# Все сенсоры (основные и диагностические)
# Порядок элементов определяет порядок отображения в интерфейсе Home Assistant
SENSOR_DESCRIPTIONS = [
    # ========== ОСНОВНЫЕ СЕНСОРЫ ==========
    SensorEntityDescription(
        key="ch0",
        translation_key="ch0",
        # native_unit_of_measurement, device_class и icon определяются динамически
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="ch1",
        translation_key="ch1",
        # native_unit_of_measurement, device_class и icon определяются динамически
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="delta0",
        translation_key="delta0",
        # native_unit_of_measurement, device_class и icon определяются динамически (как для ch0)
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="delta1",
        translation_key="delta1",
        # native_unit_of_measurement, device_class и icon определяются динамически (как для ch1)
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    
    # ========== СЕНСОРЫ КАНАЛОВ ==========
    SensorEntityDescription(
        key="ch0_start",
        translation_key="ch0_start",
        # native_unit_of_measurement, device_class и icon определяются динамически
        # state_class НЕ указан - стартовое значение не участвует в статистике (это начальное показание)
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="ch1_start",
        translation_key="ch1_start",
        # native_unit_of_measurement, device_class и icon определяются динамически
        # state_class НЕ указан - стартовое значение не участвует в статистике (это начальное показание)
        entity_category=EntityCategory.DIAGNOSTIC,
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
        # Иконка определяется динамически через icons.json
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
        # Иконка определяется динамически через icons.json
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
        key="company",
        translation_key="company",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:office-building",
    ),
    SensorEntityDescription(
        key="place",
        translation_key="place",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:map-marker",
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
    SensorEntityDescription(
        key="config_sync",
        translation_key="config_sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:sync",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WateriusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка sensor платформы."""
    if entry.runtime_data is None:
        _LOGGER.error("Runtime data не инициализирована для entry %s", entry.entry_id)
        return
    
    device_manager: DeviceManager = entry.runtime_data.device_manager
    
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
    
    # Создаем sensor для статуса Zeroconf (один для всей интеграции)
    entities.append(
        WateriusZeroconfStatusSensor(
            hass,
            entry,
        )
    )
    async_add_entities([entities[-1]], update_before_add=True)
    
    # Подписываемся на события добавления новых устройств
    setup_device_added_listener(
        hass,
        entry.entry_id,
        device_manager,
        async_add_entities,
        lambda dm, did, dn, dmac, desc: WateriusSensor(
            dm, did, dn, dmac, desc, entry.entry_id
        ),
        SENSOR_DESCRIPTIONS,
        "sensor",
    )


class WateriusSensor(WateriusEntity, SensorEntity, RestoreEntity):
    """Представление sensor для устройства Waterius.
    
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
        description: SensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Инициализация sensor."""
        super().__init__(device_manager, device_id, device_name, device_mac)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        
        # Скрываем сенсоры из HIDDEN_SENSORS по умолчанию при первом создании
        # НО: Home Assistant автоматически уважает выбор пользователя при последующих загрузках!
        # Если пользователь включил сенсор вручную, он останется включенным
        if description.key in HIDDEN_SENSORS:
            self._attr_entity_registry_enabled_default = False
        
        # Инициализация extra_state_attributes для config_sync
        if description.key == "config_sync":
            self._attr_extra_state_attributes: dict[str, Any] = {}
        
        # Инициализация для ch0 и ch1
        if self._is_channel_sensor():
            self._attr_has_entity_name = False
            self._attr_name = self._get_channel_entity_name(device_id, description.key)
            self._entity_registered = False
        else:
            self._attr_has_entity_name = True  # Для остальных сенсоров добавляем название устройства
            # НЕ устанавливаем _attr_name - Home Assistant будет использовать translation_key автоматически
        self._entry_id = entry_id
        self._unsub_update = None
        self._attr_native_value: float | int | str | datetime | None = None  # Для сохранения состояния
        # Сохраняем предыдущие значения data_type для отслеживания изменений
        self._prev_data_type_0: Any = None
        self._prev_data_type_1: Any = None
        # Переводы опций селекта "учет данных" для каналов (для динамического названия сенсоров ch0 и ch1)
        self._channel_0_data_type_translations: dict[str, str] = {}
        self._channel_1_data_type_translations: dict[str, str] = {}
    
    def _is_channel_sensor(self) -> bool:
        """Проверка, является ли сенсор каналом (ch0 или ch1)."""
        return self.entity_description.key in ("ch0", "ch1")
    
    def _get_channel_number(self) -> int:
        """Получение номера канала (0 или 1)."""
        return 0 if self.entity_description.key == "ch0" else 1
    
    def _get_short_device_id(self, device_id: str) -> str:
        """Получение короткого формата device_id (последние 4 символа MAC адреса)."""
        if device_id.startswith("waterius_"):
            # Извлекаем MAC часть после "waterius_"
            mac_part = device_id.replace("waterius_", "").replace("_", "")
            # Берем последние 4 символа и преобразуем в нижний регистр
            short_mac = mac_part[-4:].lower() if len(mac_part) >= 4 else mac_part
            return f"waterius_{short_mac}"
        # Если формат неожиданный, используем device_id как есть
        return device_id
    
    def _get_channel_entity_name(self, device_id: str, key: str) -> str:
        """Получение имени entity для канала (ch0 или ch1)."""
        short_device_id = self._get_short_device_id(device_id)
        channel_num = "0" if key == "ch0" else "1"
        return f"{short_device_id}_channel_{channel_num}"  # "waterius_705e_channel_0" или "waterius_705e_channel_1"

    async def async_added_to_hass(self) -> None:
        """Вызывается при добавлении entity в hass."""
        await super().async_added_to_hass()
        
        # Для ch0 и ch1 устанавливаем динамическое название в entity registry после регистрации
        # entity_id уже сформирован на основе _attr_name
        if self._is_channel_sensor():
            # Используем событие entity_registry_updated вместо sleep
            @callback
            def handle_entity_registry_updated(event: Event) -> None:
                """Обработка обновления entity registry для установки динамического названия."""
                if event.data.get("action") != "create":
                    return
                entity_id = event.data.get("entity_id")
                if not entity_id:
                    return
                # Проверяем, что это наш entity
                registry = er.async_get(self.hass)
                entry = registry.async_get(entity_id)
                if entry and entry.unique_id == self._attr_unique_id:
                    dynamic_name = self._get_dynamic_name()
                    # Обновляем название ТОЛЬКО если получено динамическое название
                    # Иначе оставляем существующее (не перезаписываем техническим!)
                    if dynamic_name:
                        registry.async_update_entity(entity_id, name=dynamic_name)
                        _LOGGER.debug("Установлено динамическое название для %s: %s", entity_id, dynamic_name)
                    else:
                        _LOGGER.debug("Динамическое название не получено для %s, оставляем существующее", entity_id)
                    # Отменяем подписку после успешной установки
                    if hasattr(self, "_unsub_entity_registry"):
                        self._unsub_entity_registry()
                        self._unsub_entity_registry = None
            
            # Подписываемся на событие обновления entity registry
            self._unsub_entity_registry = self.hass.bus.async_listen(
                "entity_registry_updated",
                handle_entity_registry_updated,
            )
        
        # Восстанавливаем последнее сохраненное состояние
        # Также сохраняем предыдущие единицы измерения для проверки реальных изменений
        self._had_previous_state = False  # Флаг: был ли сенсор активен раньше
        self._prev_unit_of_measurement = None  # Предыдущие единицы измерения
        
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
                    
                    # Сохраняем предыдущие единицы измерения для динамических сенсоров
                    if self._is_channel_sensor() or self.entity_description.key in ("delta0", "delta1", "ch0_start", "ch1_start"):
                        if hasattr(last_state, "attributes") and "unit_of_measurement" in last_state.attributes:
                            self._prev_unit_of_measurement = last_state.attributes["unit_of_measurement"]
                            self._had_previous_state = True
                            _LOGGER.debug(
                                "Восстановлены предыдущие единицы измерения для %s: %s",
                                self.entity_description.key,
                                self._prev_unit_of_measurement
                            )
                except (ValueError, TypeError) as e:
                    _LOGGER.debug("Не удалось восстановить состояние для %s: %s", self.entity_id, e)
        
        # Загружаем переводы опций селекта "учет данных" для ch0 и ch1 (для динамического названия)
        if self._is_channel_sensor():
            channel = self._get_channel_number()
            translations_dict = self._channel_0_data_type_translations if channel == 0 else self._channel_1_data_type_translations
            
            # Используем общую функцию для загрузки переводов
            loaded_translations = await load_translations_from_json(
                self.hass,
                self.hass.config.language,
                "select",
                f"channel_{channel}_data_type_data",
            )
            
            # Копируем загруженные переводы в словарь (используем COUNTER_NAME для cname)
            for option in COUNTER_NAME_OPTIONS:
                if option in loaded_translations:
                    translations_dict[option] = loaded_translations[option]
            
            _LOGGER.debug(
                "Загружены переводы для канала %d: %d опций",
                channel,
                len(translations_dict)
            )
            
            # ПОСЛЕ загрузки переводов устанавливаем динамическое название
            # Пытаемся установить сразу, если entity уже зарегистрирован
            registry = er.async_get(self.hass)
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, self._attr_unique_id)
            if entity_id:
                # Получаем устройство для чтения data_type
                device_for_naming = self._device_manager.get_device(self._device_id)
                data_type_value = device_for_naming.data.get(f"data_type{channel}") if device_for_naming and device_for_naming.data else None
                
                dynamic_name = self._get_dynamic_name()
                # Обновляем название ТОЛЬКО если получено динамическое название
                # Иначе оставляем существующее (не перезаписываем техническим!)
                if dynamic_name:
                    registry.async_update_entity(entity_id, name=dynamic_name)
                    _LOGGER.debug("Установлено название для %s: %s", entity_id, dynamic_name)
                else:
                    _LOGGER.debug("Динамическое название не получено для %s, оставляем существующее", entity_id)
                if hasattr(self, "_unsub_entity_registry") and self._unsub_entity_registry:
                    self._unsub_entity_registry()
                    self._unsub_entity_registry = None
        
        # Инициализируем предыдущие значения data_type из device.data
        device = self._device_manager.get_device(self._device_id)
        if device and device.data:
            if self.entity_description.key in ("ch0", "ch0_start"):
                self._prev_data_type_0 = device.data.get("cname0")  # ⚡ ИЗМЕНЕНО: было data_type0
            elif self.entity_description.key in ("ch1", "ch1_start"):
                self._prev_data_type_1 = device.data.get("cname1")  # ⚡ ИЗМЕНЕНО: было data_type1
        
        # Подписываемся на события обновления устройства
        @callback
        def handle_device_update(event: Event) -> None:
            """Обработка обновления данных устройства."""
            # ✅ НОВАЯ АРХИТЕКТУРА: Все сенсоры обновляются ТОЛЬКО от устройства!
            # Select/Number больше НЕ генерируют события с source="user"
            # device.data обновляется ТОЛЬКО от устройства
            # Сенсоры читают из device.data → всегда текущее состояние устройства!
            
            if event.data.get("device_id") == self._device_id:
                device = self._device_manager.get_device(self._device_id)
                
                # Проверяем источник события
                event_source = event.data.get("source")
                
                # Проверяем, изменился ли тип данных для каналов
                data_type_changed = False
                
                # ⚡ ВАЖНО: Если событие от изменения select data_type, принудительно обновляем!
                if event_source == "data_type_change":
                    # Пользователь изменил select типа данных → нужно обновить device_class и unit
                    if self.entity_description.key in ("ch0", "ch0_start", "delta0", "ch1", "ch1_start", "delta1"):
                        data_type_changed = True
                        _LOGGER.info(
                            "🔄 Принудительное обновление device_class/unit для %s (source=data_type_change)",
                            self.entity_description.key
                        )
                elif device and device.data:
                    # Обычное обновление от устройства: проверяем изменение в device.data
                    if self.entity_description.key in ("ch0", "ch0_start", "delta0"):
                        current_data_type = device.data.get("cname0")  # ⚡ ИЗМЕНЕНО: было data_type0
                        if current_data_type != self._prev_data_type_0:
                            data_type_changed = True
                            self._prev_data_type_0 = current_data_type
                    elif self.entity_description.key in ("ch1", "ch1_start", "delta1"):
                        current_data_type = device.data.get("cname1")  # ⚡ ИЗМЕНЕНО: было data_type1
                        if current_data_type != self._prev_data_type_1:
                            data_type_changed = True
                            self._prev_data_type_1 = current_data_type
                
                # Обновляем информацию об устройстве в device registry
                self._update_device_info()
                
                # Если изменился тип данных, обновляем unit, device_class и icon
                if data_type_changed:
                    registry = er.async_get(self.hass)
                    entity_id = registry.async_get_entity_id("sensor", DOMAIN, self._attr_unique_id)
                    
                    if entity_id:
                        # Получаем новые unit, device_class и icon
                        channel = 0 if self.entity_description.key in ("ch0", "ch0_start", "delta0") else 1
                        data_type = self._get_data_type_string(channel)
                        new_unit, new_device_class = self._get_unit_and_device_class(data_type)
                        new_icon = self._get_icon_for_data_type(data_type)
                        
                        # Для ch0/ch1 также обновляем динамическое название
                        if self._is_channel_sensor():
                            # Получаем динамическое название для отображения
                            dynamic_name = self._get_dynamic_name()
                            
                            _LOGGER.debug(
                                "Обновление для %s: dynamic_name=%s, новая иконка=%s (unit=%s, device_class=%s)", 
                                entity_id, 
                                dynamic_name,
                                new_icon,
                                new_unit,
                                new_device_class
                            )
                            
                            # Обновляем иконку всегда, но название ТОЛЬКО если получено динамическое название
                            # Если dynamic_name is None, оставляем существующее название (не перезаписываем техническим!)
                            if dynamic_name:
                                # Обновляем и название, и иконку
                                registry.async_update_entity(entity_id, name=dynamic_name, icon=new_icon)
                                _LOGGER.debug("Обновлено название для %s: %s", entity_id, dynamic_name)
                            else:
                                # Обновляем только иконку, название оставляем как есть
                                registry.async_update_entity(entity_id, icon=new_icon)
                                _LOGGER.debug("Обновлена только иконка для %s (название сохранено)", entity_id)
                            
                            # Создаем уведомление об изменении единиц измерения
                            # ТОЛЬКО если:
                            # 1. Сенсор работал раньше (имел сохраненное состояние)
                            # 2. Единицы измерения реально изменились
                            old_unit = getattr(self, "_prev_unit_of_measurement", None)
                            had_previous_state = getattr(self, "_had_previous_state", False)
                            
                            if had_previous_state and old_unit and old_unit != new_unit:
                                try:
                                    # Получаем запись из entity registry для отображаемого имени
                                    entity_entry = registry.async_get(entity_id)
                                    display_name = dynamic_name if dynamic_name else (entity_entry.name if entity_entry else entity_id)
                                    
                                    from homeassistant.components import persistent_notification
                                    persistent_notification.async_create(
                                        self.hass,
                                        title="Изменены единицы измерения сенсора",
                                        message=(
                                            f"Для сенсора **{display_name}** (`{entity_id}`) изменились единицы измерения: "
                                            f"**{old_unit}** → **{new_unit}**.\n\n"
                                            f"Если ранее для этого сенсора собиралась статистика в других единицах, "
                                            f"рекомендуется проверить и при необходимости исправить статистику:\n\n"
                                            f"[Перейти к статистике ↗]"
                                            f"(https://my.home-assistant.io/redirect/developer_statistics)\n\n"
                                            f"Это уведомление можно закрыть."
                                        ),
                                        notification_id=f"waterius_unit_change_{entity_id.replace('.', '_')}",
                                    )
                                    _LOGGER.info(
                                        "Создано уведомление об изменении единиц для %s: %s → %s",
                                        entity_id,
                                        old_unit,
                                        new_unit
                                    )
                                except Exception as e:
                                    _LOGGER.debug("Не удалось создать уведомление об изменении единиц: %s", e)
                            elif had_previous_state:
                                _LOGGER.debug(
                                    "Единицы измерения не изменились для %s (было: %s, стало: %s), уведомление не создается",
                                    entity_id,
                                    old_unit,
                                    new_unit
                                )
                            else:
                                _LOGGER.debug(
                                    "Сенсор %s активирован впервые или не имел сохраненного состояния, уведомление не создается",
                                    entity_id
                                )
                            
                            # Обновляем сохраненные единицы измерения для следующего раза
                            self._prev_unit_of_measurement = new_unit
                            self._had_previous_state = True
                        else:
                            # Для delta0, delta1, ch0_start, ch1_start обновляем только иконку
                            _LOGGER.debug(
                                "Обновлена иконка для %s: %s (unit=%s, device_class=%s, icon=%s)", 
                                entity_id,
                                self.name,
                                new_unit,
                                new_device_class,
                                new_icon
                            )
                            
                            # Обновляем только иконку
                            registry.async_update_entity(entity_id, icon=new_icon)
                    
                    # Принудительно обновляем состояние для всех сенсоров с динамическими единицами,
                    # чтобы Home Assistant перечитал все свойства (unit_of_measurement, device_class, icon)
                    # ВАЖНО: используем force_refresh=True для полного обновления всех свойств
                    self.async_schedule_update_ha_state(force_refresh=True)
                else:
                    # Для сенсоров с динамическими единицами всегда используем force_refresh
                    # чтобы избежать конфликта между unit и device_class
                    key = self.entity_description.key
                    if key in ("ch0", "ch1", "delta0", "delta1", "ch0_start", "ch1_start"):
                        # Динамические сенсоры - принудительное полное обновление
                        self.async_schedule_update_ha_state(force_refresh=True)
                    else:
                        # Обычные сенсоры - простое обновление состояния
                        self.async_write_ha_state()
        
        self._unsub_update = self.hass.bus.async_listen(
            "waterius_device_update", handle_device_update
        )
        
        # ВАЖНО: Если устройство уже имеет данные (добавлено раньше, чем созданы entities),
        # то инициализируем сенсор сразу, не дожидаясь первого события
        # Это особенно важно для сенсоров, которые были включены из disabled состояния
        device = self._device_manager.get_device(self._device_id)
        if device and device.data and self.entity_description.key in device.data:
            # Данные есть - явно устанавливаем значение и обновляем состояние
            value = device.data.get(self.entity_description.key)
            _LOGGER.debug(
                "Инициализация сенсора %s значением из device.data: %s",
                self.entity_description.key,
                value
            )
            # Явно устанавливаем значение через _process_value для правильной обработки
            if value is not None:
                self._attr_native_value = self._process_value(value)
            
            # Используем async_create_task для немедленного обновления без блокировки
            # Task выполнится после завершения текущей корутины (async_added_to_hass)
            async def _force_update() -> None:
                """Принудительное обновление состояния после инициализации."""
                _LOGGER.debug(
                    "Принудительное обновление сенсора %s: %s",
                    self.entity_description.key,
                    self._attr_native_value
                )
                # Принудительное обновление - заставляет HA прочитать native_value property
                self.async_schedule_update_ha_state(force_refresh=True)
            
            # Создаем task который выполнится сразу после завершения async_added_to_hass
            self.hass.async_create_task(_force_update())
        else:
            # Если данных еще нет, запланируем обновление при следующем событии
            _LOGGER.debug(
                "Сенсор %s создан, но данных пока нет (device_exists=%s, has_data=%s, key_in_data=%s)",
                self.entity_description.key,
                device is not None,
                device.data is not None if device else False,
                self.entity_description.key in device.data if (device and device.data) else False
            )


    @property
    def device_info(self) -> DeviceInfo:
        """Информация об устройстве."""
        device = self._device_manager.get_device(self._device_id)
        device_data = device.data if device else None
        return get_device_info(
            self._device_manager,
            self._device_id,
            self._device_name,
            self._device_mac,
            device_data,
        )

    def _get_dynamic_name(self) -> str | None:
        """Получение динамического названия для ch0 и ch1.
        
        ⚡ ВАЖНО: Читаем тип данных из SELECT ENTITY через _get_data_type_string(),
        а не напрямую из device.data. Это позволяет обновлять название сразу при
        изменении select, а не только при получении данных от устройства.
        """
        # Определяем канал (0 или 1)
        channel = 0 if self.entity_description.key == "ch0" else 1
        translations_dict = self._channel_0_data_type_translations if channel == 0 else self._channel_1_data_type_translations
        
        # Получаем тип данных из select entity (или fallback на device.data)
        data_type_string = self._get_data_type_string(channel)
        
        if not data_type_string:
            return None
        
        # Если выбрано "OTHER", используем стандартное название
        if data_type_string == "OTHER":
            return None
        
        # Получаем переведенное значение из загруженных переводов
        if data_type_string in translations_dict:
            translated_name = translations_dict[data_type_string]
            _LOGGER.debug(
                "[%s] Динамическое название для канала %d: '%s' (%s)",
                self.entity_description.key,
                channel,
                translated_name,
                data_type_string
            )
            return translated_name
        
        _LOGGER.warning(
            "[%s] Перевод не найден для %s (канал %d)",
            self.entity_description.key,
            data_type_string,
            channel
        )
        
        return None
    
    def __getattribute__(self, name: str) -> Any:
        """Переопределение для условного доступа к свойству name."""
        # Используем object.__getattribute__ для избежания рекурсии
        if name == "name":
            # Для ch0 и ch1 ВСЕГДА возвращаем _attr_name для правильного формирования entity_id
            # Динамическое название устанавливается через entity registry после регистрации
            entity_key = object.__getattribute__(self, "entity_description").key
            if entity_key in ("ch0", "ch1"):
                attr_name = object.__getattribute__(self, "_attr_name")
                return attr_name  # "channel_0" или "channel_1"
            # Для остальных сенсоров НЕ переопределяем name
            # Home Assistant автоматически использует translation_key из entity_description
            # Используем базовую реализацию через super()
            return super().__getattribute__(name)
        return super().__getattribute__(name)
    
    def _get_data_type_string(self, channel: int) -> str | None:
        """Получение строки типа данных для канала из SELECT ENTITY.
        
        ⚡ ВАЖНО: Читаем data_type из SELECT, а не из device.data!
        Это позволяет динамически менять device_class и unit при изменении select,
        при этом сохраняя возможность видеть разницу через config_sync.
        """
        # Ищем entity через Entity Registry по unique_id
        registry = er.async_get(self.hass)
        unique_id = f"{self._device_id}_channel_{channel}_data_type_data_config"
        entity_id = registry.async_get_entity_id("select", DOMAIN, unique_id)
        
        if not entity_id:
            # Entity не найден в registry, используем device.data как fallback
            _LOGGER.debug(
                "Select с unique_id=%s не найден в registry, используем device.data как fallback",
                unique_id
            )
            device = self._device_manager.get_device(self._device_id)
            if not device or not device.data:
                return None
            data_type_value = device.data.get(f"cname{channel}")  # ⚡ ИЗМЕНЕНО: было data_type{channel}
            if data_type_value is None:
                return None
            
            # Используем helper функцию для преобразования (CounterName для cname)
            from .const import convert_value_to_counter_name  # ⚡ ИЗМЕНЕНО
            return convert_value_to_counter_name(data_type_value)
        
        # Получаем state select entity
        state = self.hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            # Если select недоступен, пробуем device.data как fallback
            _LOGGER.debug(
                "Select %s (unique_id=%s) недоступен (state=%s), используем device.data как fallback",
                entity_id,
                unique_id,
                state.state if state else "None"
            )
            device = self._device_manager.get_device(self._device_id)
            if not device or not device.data:
                return None
            data_type_value = device.data.get(f"cname{channel}")  # ⚡ ИЗМЕНЕНО: было data_type{channel}
            if data_type_value is None:
                return None
            
            # Используем helper функцию для преобразования (CounterName для cname)
            from .const import convert_value_to_counter_name  # ⚡ ИЗМЕНЕНО
            return convert_value_to_counter_name(data_type_value)
        
        # Читаем internal_option из атрибутов select
        internal_option = state.attributes.get("internal_option")
        if internal_option:
            return internal_option
        
        # Если internal_option отсутствует, пробуем преобразовать internal_value
        internal_value = state.attributes.get("internal_value")
        if internal_value is not None:
            from .const import convert_value_to_counter_name  # ⚡ ИЗМЕНЕНО: для cname
            return convert_value_to_counter_name(internal_value)
        
        return None

    def _get_unit_and_device_class(self, data_type: str | None) -> tuple[str | None, SensorDeviceClass | None]:
        """Определение единиц измерения и device_class на основе типа данных.
        
        Использует словарь маппинга для O(1) производительности.
        """
        if not data_type:
            # Значения по умолчанию (вода)
            return UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER
        
        # Используем словарь маппинга для быстрого поиска
        return _DATA_TYPE_MAPPING.get(
            data_type,
            (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER)  # default
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Единица измерения сенсора (динамически определяется для ch0, ch1, delta0, delta1, ch0_start, ch1_start)."""
        # Для сенсоров каналов определяем единицы измерения динамически
        if self.entity_description.key in ("ch0", "ch0_start", "delta0"):
            data_type = self._get_data_type_string(0)
            unit, _ = self._get_unit_and_device_class(data_type)
            return unit
        elif self.entity_description.key in ("ch1", "ch1_start", "delta1"):
            data_type = self._get_data_type_string(1)
            unit, _ = self._get_unit_and_device_class(data_type)
            return unit
        
        # Для остальных сенсоров используем значение из описания
        return self.entity_description.native_unit_of_measurement

    @property
    def state_class(self) -> SensorStateClass | str | None:
        """State class сенсора (динамически определяется для ch0, ch1, delta0, delta1)."""
        # Для сенсоров каналов с кастомными единицами (Gcal) отключаем state_class
        # чтобы избежать ошибок конвертации статистики
        key = self.entity_description.key
        if key in ("ch0", "ch1", "delta0", "delta1"):
            # Проверяем, является ли единица измерения кастомной
            channel = 0 if key in ("ch0", "delta0") else 1
            data_type = self._get_data_type_string(channel)
            unit, _ = self._get_unit_and_device_class(data_type)
            
            # Для Gcal (нестандартная единица) отключаем state_class
            if unit == "Gcal":
                _LOGGER.debug(
                    "[%s] state_class=None для кастомной единицы Gcal",
                    self.entity_description.key
                )
                return None
            
            # Для стандартных единиц используем значение из описания
            return self.entity_description.state_class
        
        # Для остальных сенсоров используем значение из описания
        return self.entity_description.state_class

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Класс устройства сенсора (динамически определяется для ch0, ch1, delta0, delta1, ch0_start, ch1_start)."""
        # Для сенсоров каналов определяем device_class динамически
        key = self.entity_description.key
        if key in ("ch0", "ch0_start", "delta0"):
            data_type = self._get_data_type_string(0)
            _, device_class = self._get_unit_and_device_class(data_type)
            return device_class
        elif key in ("ch1", "ch1_start", "delta1"):
            data_type = self._get_data_type_string(1)
            _, device_class = self._get_unit_and_device_class(data_type)
            return device_class
        
        # Для остальных сенсоров используем значение из описания
        return self.entity_description.device_class

    def _get_icon_for_data_type(self, data_type: str | None) -> str:
        """Определение иконки на основе типа данных."""
        if not data_type:
            return "mdi:water"
        
        # Иконки для разных типов данных
        icon_map = {
            "WATER_COLD": "mdi:water",
            "WATER_HOT": "mdi:water-boiler",
            "PORTABLE_WATER": "mdi:water-pump",
            "GAS": "mdi:fire",
            "ELECTRO": "mdi:lightning-bolt",
            "HEAT_GCAL": "mdi:radiator",
            "HEAT_KWT": "mdi:radiator",
            "OTHER": "mdi:counter",
        }
        
        return icon_map.get(data_type, "mdi:counter")

    @property
    def icon(self) -> str | None:
        """Иконка сенсора (динамически определяется для ch0, ch1, delta0, delta1, ch0_start, ch1_start)."""
        # Для сенсоров каналов определяем иконку динамически
        key = self.entity_description.key
        if key in ("ch0", "ch0_start", "delta0"):
            data_type = self._get_data_type_string(0)
            return self._get_icon_for_data_type(data_type)
        elif key in ("ch1", "ch1_start", "delta1"):
            data_type = self._get_data_type_string(1)
            return self._get_icon_for_data_type(data_type)
        
        # Для остальных сенсоров используем значение из описания
        return self.entity_description.icon

    @property
    def native_value(self) -> float | int | str | bool | datetime | None:
        """Текущее значение sensor."""
        # Специальная обработка для сенсора синхронизации конфигурации
        if self.entity_description.key == "config_sync":
            return self._get_config_sync_status()
        
        device = self._device_manager.get_device(self._device_id)
        
        # Если есть данные устройства, используем их
        if device and device.data:
            value = device.data.get(self.entity_description.key)
            if value is not None:
                processed_value = self._process_value(value)
                self._attr_native_value = processed_value
                return processed_value
        
        # Если данных нет, возвращаем сохраненное значение
        return self._attr_native_value
    
    def _process_value(self, value: Any) -> float | int | str | bool | datetime | None:
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
        
        # Для числовых значений
        try:
            if self.entity_description.key in INTEGER_SENSOR_KEYS:
                # Для целочисленных сенсоров возвращаем int
                return int(float(value))
            else:
                # Для остальных возвращаем float
                return float(value)
        except (ValueError, TypeError):
            return str(value) if value is not None else None

    def _get_config_sync_status(self) -> str:
        """Проверка синхронизации конфигурации между Select/Number и Sensor.
        
        Сравнивает:
        - Желаемое состояние: из select/number entities (то что хочет пользователь)
        - Текущее состояние: из device.data (то что сейчас на устройстве)
        """
        device = self._device_manager.get_device(self._device_id)
        if not device or not device.data:
            return "unknown"
        
        # Получаем entity registry для поиска entity по unique_id
        registry = er.async_get(self.hass)
        
        # Маппинг: параметр устройства → (unique_id_suffix, domain)
        # ⚡ ВАЖНО: Должно совпадать с web_server.py::_build_settings_json()
        config_params = {
            "ctype0": ("channel_0_data_type_config", "select"),
            "ctype1": ("channel_1_data_type_config", "select"),
            "cname0": ("channel_0_data_type_data_config", "select"),
            "cname1": ("channel_1_data_type_data_config", "select"), 
            "f0": ("channel_0_conversion_factor_config", "select"),
            "f1": ("channel_1_conversion_factor_config", "select"),
            "period_min": ("period_min_config", "number"),
        }
        
        differences = {}
        checked_params = 0  # Счетчик успешно проверенных параметров
        
        for param_key, (unique_id_suffix, domain) in config_params.items():
            # Значение на устройстве (текущее состояние)
            device_value = device.data.get(param_key)
            if device_value is None:
                _LOGGER.debug(
                    "[config_sync] Параметр %s отсутствует в device.data, пропускаем",
                    param_key
                )
                continue
            
            # Формируем полный unique_id и ищем entity через registry
            unique_id = f"{self._device_id}_{unique_id_suffix}"
            entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
            
            if not entity_id:
                _LOGGER.debug(
                    "[config_sync] Entity с unique_id=%s не найден в registry",
                    unique_id
                )
                continue
            
            # Получаем state entity
            state = self.hass.states.get(entity_id)
            if not state or state.state in ("unknown", "unavailable"):
                _LOGGER.debug(
                    "[config_sync] Entity %s (unique_id=%s) недоступен (state=%s), пропускаем проверку",
                    entity_id,
                    unique_id,
                    state.state if state else "None"
                )
                continue
            
            # Получаем значение из select/number (желаемое состояние)
            try:
                device_value_int = int(float(device_value))
                
                # Для select
                if domain == "select":
                    # Для conversion_factor: читаем напрямую из state (уже числовое значение)
                    if param_key in ("f0", "f1"):
                        user_value = int(state.state)
                    # Для остальных select: читаем internal_value из атрибутов
                    else:
                        user_value = state.attributes.get("internal_value")
                        if user_value is None:
                            _LOGGER.debug(
                                "[config_sync] Не найден internal_value для %s (entity_id=%s, unique_id=%s)",
                                param_key,
                                entity_id,
                                unique_id
                            )
                            continue
                        user_value = int(user_value)
                # Для number: читаем state
                elif domain == "number":
                    user_value = int(float(state.state))
                
                # Успешно проверили параметр
                checked_params += 1
                
                # Сравниваем желаемое (user_value) с текущим (device_value_int)
                if user_value != device_value_int:
                    differences[param_key] = {
                        "desired": user_value,
                        "current": device_value_int
                    }
                    _LOGGER.debug(
                        "[config_sync] Расхождение для %s: desired=%s, current=%s",
                        param_key,
                        user_value,
                        device_value_int
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.debug(
                    "[config_sync] Ошибка сравнения %s: state=%s, device=%s, error=%s",
                    param_key,
                    state.state if state else None,
                    device_value,
                    e
                )
                continue
        
        # Если ни один параметр не был успешно проверен, возвращаем unknown
        if checked_params == 0:
            _LOGGER.debug(
                "[config_sync] ⚠️ Ни один параметр не был проверен для %s (entities недоступны)",
                self._device_id
            )
            self._attr_extra_state_attributes = {"checked_params": 0}
            return "unknown"
        
        # Обновляем атрибуты с информацией о различиях
        if differences:
            self._attr_extra_state_attributes = {
                "differences": differences,
                "count": len(differences),
                "checked_params": checked_params
            }
            _LOGGER.info(
                "[config_sync] 🔴 Настройки НЕ синхронизированы для %s: %d расхождений из %d проверенных",
                self._device_id,
                len(differences),
                checked_params
            )
            return "not_synchronized"
        else:
            self._attr_extra_state_attributes = {
                "count": 0,
                "checked_params": checked_params
            }
            _LOGGER.debug(
                "[config_sync] ✅ Настройки синхронизированы для %s (%d параметров проверено)",
                self._device_id,
                checked_params
            )
            return "synchronized"

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
            identifiers = get_device_identifiers(self._device_id, self._device_mac)
            
            device_entry = dev_reg.async_get_device(identifiers=identifiers)
            if not device_entry:
                return
            
            # Используем общие функции для получения данных
            sw_version = get_software_version(device.data)
            serial_number = device.data.get("key")
            ip_address = device.data.get("ip")
            configuration_url = get_configuration_url(ip_address)
            
            # Обновляем информацию об устройстве
            # НО: обновляем только те поля, для которых есть данные
            # Это предотвращает затирание существующих значений при перезагрузке
            update_data = {"hw_version": DEVICE_HW_VERSION}
            
            if sw_version is not None:
                update_data["sw_version"] = sw_version
            
            if serial_number is not None:
                update_data["serial_number"] = serial_number
            
            if configuration_url is not None:
                update_data["configuration_url"] = configuration_url
            
            dev_reg.async_update_device(device_entry.id, **update_data)
        except Exception as e:
            _LOGGER.warning("Ошибка при обновлении информации об устройстве: %s", e)


class WateriusZeroconfStatusSensor(SensorEntity):
    """Sensor для отображения статуса регистрации Zeroconf сервиса."""
    
    _attr_has_entity_name = True
    _attr_translation_key = "zeroconf_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:network"
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry: WateriusConfigEntry,
    ) -> None:
        """Инициализация sensor статуса Zeroconf.
        
        Args:
            hass: Экземпляр Home Assistant
            entry: Config entry интеграции
        """
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zeroconf_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Waterius Integration",
            manufacturer=DEVICE_MANUFACTURER,
        )
        self._attr_native_value = None
        self._unsub_update = None
    
    @property
    def native_value(self) -> str | None:
        """Возвращает текущий статус Zeroconf."""
        if self._entry.runtime_data is None:
            return "unknown"
        
        if self._entry.runtime_data.zeroconf_registered:
            return "registered"
        return "not_registered"
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Возвращает дополнительные атрибуты сенсора - данные, передаваемые устройствам через Zeroconf."""
        attrs: dict[str, Any] = {}
        
        if self._entry.runtime_data:
            attrs["zeroconf_registered"] = self._entry.runtime_data.zeroconf_registered
            
            if self._entry.runtime_data.zeroconf_service_info:
                service_info = self._entry.runtime_data.zeroconf_service_info
                
                # Данные, передаваемые через Zeroconf
                attrs["service_name"] = service_info.name
                attrs["service_type"] = service_info.type
                attrs["server"] = service_info.server
                attrs["port"] = service_info.port
                
                # Преобразуем бинарные адреса в строки
                if service_info.addresses:
                    addresses = []
                    for addr in service_info.addresses:
                        try:
                            addresses.append(socket.inet_ntoa(addr))
                        except (OSError, ValueError):
                            pass
                    
                    if addresses:
                        attrs["addresses"] = addresses
                    
                # Properties из Zeroconf
                if service_info.properties:
                    attrs["properties"] = {
                        k.decode() if isinstance(k, bytes) else k: 
                        v.decode() if isinstance(v, bytes) else v 
                        for k, v in service_info.properties.items()
                    }
            
            # Hostname из настроек HA (для справки, не передается через Zeroconf)
            if self._entry.runtime_data.ha_hostname:
                attrs["ha_hostname"] = self._entry.runtime_data.ha_hostname
        
        return attrs
    
    async def async_added_to_hass(self) -> None:
        """Вызывается при добавлении entity в hass."""
        await super().async_added_to_hass()
        
        # Подписываемся на события обновления статуса Zeroconf
        @callback
        def handle_zeroconf_status_changed(event: Event) -> None:
            """Обработка изменения статуса Zeroconf."""
            if event.data.get("entry_id") == self._entry.entry_id:
                self.async_write_ha_state()
        
        self._unsub_update = self.hass.bus.async_listen(
            "waterius_zeroconf_status_changed",
            handle_zeroconf_status_changed,
        )
        
        # Обновляем статус сразу
        self.async_write_ha_state()
    
    async def async_will_remove_from_hass(self) -> None:
        """Вызывается при удалении entity из hass."""
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        await super().async_will_remove_from_hass()

