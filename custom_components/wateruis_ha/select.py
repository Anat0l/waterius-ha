"""Select platform для интеграции Waterius."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.translation import async_get_translations

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MAC,
)
from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)

# Опции для типа канала (ctype)
CHANNEL_TYPE_OPTIONS = ["MECHANIC", "ELECTRONIC", "NOT_USED"]

# Опции для типа данных канала (data_type)
DATA_TYPE_OPTIONS = [
    "WATER_COLD",
    "WATER_HOT",
    "ELECTRO",
    "GAS",
    "HEAT_GCAL",
    "PORTABLE_WATER",
    "OTHER",
    "HEAT_KWT",
]

# Опции для коэффициента пересчета (f0, f1)
CONVERSION_FACTOR_OPTIONS = ["1", "10", "100"]

# Описания select entities
SELECT_DESCRIPTIONS = [
    SelectEntityDescription(
        key="channel_0_data_type",
        translation_key="channel_0_data_type",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:format-list-bulleted-type",
    ),
    SelectEntityDescription(
        key="channel_1_data_type",
        translation_key="channel_1_data_type",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:format-list-bulleted-type",
    ),
    SelectEntityDescription(
        key="channel_0_data_type_data",
        translation_key="channel_0_data_type_data",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:format-list-bulleted-type",
    ),
    SelectEntityDescription(
        key="channel_1_data_type_data",
        translation_key="channel_1_data_type_data",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:format-list-bulleted-type",
    ),
    SelectEntityDescription(
        key="channel_0_conversion_factor",
        translation_key="channel_0_conversion_factor",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:calculator",
    ),
    SelectEntityDescription(
        key="channel_1_conversion_factor",
        translation_key="channel_1_conversion_factor",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:calculator",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка select платформы."""
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        return

    entry_data = hass.data[DOMAIN][entry.entry_id]
    device_manager: DeviceManager = entry_data.get("device_manager")

    if not device_manager:
        return

    # Создаем select entities для всех устройств
    entities = []
    devices = entry.data.get(CONF_DEVICES, [])
    
    for device_config in devices:
        device_id = device_config.get(CONF_DEVICE_ID)
        device_name = device_config.get(CONF_DEVICE_NAME)
        device_mac = device_config.get(CONF_DEVICE_MAC)
        
        if not device_id or not device_name:
            continue
        
        # Создаем select entities для каждого канала
        for description in SELECT_DESCRIPTIONS:
            entities.append(
                WateriusSelect(
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
        
        # Создаем select entities для нового устройства
        new_entities = []
        for description in SELECT_DESCRIPTIONS:
            new_entities.append(
                WateriusSelect(
                    device_manager,
                    device_id,
                    device_name,
                    device_mac,
                    description,
                    entry,
                )
            )
        
        async_add_entities(new_entities, update_before_add=True)
        _LOGGER.info("Созданы select entities для устройства %s", device_name)
    
    hass.bus.async_listen("waterius_device_added", handle_device_added)


class WateriusSelect(SelectEntity, RestoreEntity):
    """Представление select для типа канала устройства Waterius."""

    def __init__(
        self,
        device_manager: DeviceManager,
        device_id: str,
        device_name: str,
        device_mac: str | None,
        description: SelectEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Инициализация select."""
        self._device_manager = device_manager
        self._device_id = device_id
        self._device_name = device_name
        self._device_mac = device_mac
        self._base_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_has_entity_name = True
        self._entry = entry
        # Внутренние значения для работы с данными устройства
        self._internal_options = None
        # Определяем опции в зависимости от типа select entity
        if description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            self._attr_options = DATA_TYPE_OPTIONS
            self._internal_options = DATA_TYPE_OPTIONS
        elif description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
            self._attr_options = CONVERSION_FACTOR_OPTIONS
            self._internal_options = CONVERSION_FACTOR_OPTIONS
        else:
            # Для channel_0_data_type и channel_1_data_type опции будут переведены в async_added_to_hass
            self._attr_options = CHANNEL_TYPE_OPTIONS
            self._internal_options = CHANNEL_TYPE_OPTIONS
        self._attr_current_option = None
        self._option_translation_map = {}  # Маппинг между переведенными и внутренними значениями
        self._internal_current_option = None  # Внутреннее значение для работы с данными

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
    def entity_description(self) -> SelectEntityDescription:
        """Описание entity."""
        return self._base_description

    async def async_added_to_hass(self) -> None:
        """Вызывается при добавлении entity в hass."""
        await super().async_added_to_hass()
        
        # Для селектов с переводами загружаем переводы опций
        if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type", "channel_0_data_type_data", "channel_1_data_type_data"):
            translations = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "select",
                [DOMAIN]
            )
            
            # Формируем ключ для переводов опций
            translation_key = f"component.{DOMAIN}.select.{self.entity_description.key}.state"
            
            # Определяем список опций для перевода
            if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
                options_to_translate = CHANNEL_TYPE_OPTIONS
            else:
                options_to_translate = DATA_TYPE_OPTIONS
            
            # Создаем переведенные опции и маппинг
            translated_options = []
            reverse_map = {}  # Маппинг от переведенного значения к внутреннему
            
            for internal_option in options_to_translate:
                # Пытаемся получить перевод
                translation_path = f"{translation_key}.{internal_option}"
                translated = translations.get(translation_path, internal_option)
                translated_options.append(translated)
                reverse_map[translated] = internal_option
            
            # Обновляем опции
            self._attr_options = translated_options
            self._option_translation_map = reverse_map
        
        # Восстанавливаем последнее сохраненное состояние
        restored_state = None
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable", None):
                restored_state = last_state.state
                # Если это переведенное значение, конвертируем обратно во внутреннее
                if self._option_translation_map and restored_state in self._option_translation_map:
                    restored_state = self._option_translation_map[restored_state]
                self._attr_current_option = restored_state
                _LOGGER.debug(
                    "Восстановлено сохраненное состояние для %s: %s",
                    self.entity_description.key,
                    restored_state
                )
        
        # Загружаем значение из сенсора
        # Приоритет: данные от устройства > сохраненное состояние
        device = self._device_manager.get_device(self._device_id)
        if device and device.data:
            # Определяем ключ сенсора
            sensor_key = None
            if self.entity_description.key == "channel_0_data_type":
                sensor_key = "ctype0"
            elif self.entity_description.key == "channel_1_data_type":
                sensor_key = "ctype1"
            elif self.entity_description.key == "channel_0_data_type_data":
                sensor_key = "data_type0"
            elif self.entity_description.key == "channel_1_data_type_data":
                sensor_key = "data_type1"
            elif self.entity_description.key == "channel_0_conversion_factor":
                sensor_key = "f0"
            elif self.entity_description.key == "channel_1_conversion_factor":
                sensor_key = "f1"
            
            # Если есть данные от устройства, используем их
            if sensor_key and sensor_key in device.data:
                sensor_value = self._convert_type_to_option(device.data.get(sensor_key))
                # Сохраняем внутреннее значение
                self._internal_current_option = sensor_value
                # Отображаем переведенное значение
                if self._option_translation_map and sensor_value in self._option_translation_map.values():
                    for translated, internal in self._option_translation_map.items():
                        if internal == sensor_value:
                            self._attr_current_option = translated
                            break
                    else:
                        self._attr_current_option = sensor_value
                else:
                    self._attr_current_option = sensor_value
            elif restored_state is not None:
                # Если данных от устройства нет, но есть сохраненное состояние, используем его
                self._internal_current_option = restored_state
                # Отображаем переведенное значение
                if self._option_translation_map and restored_state in self._option_translation_map.values():
                    for translated, internal in self._option_translation_map.items():
                        if internal == restored_state:
                            self._attr_current_option = translated
                            break
                    else:
                        self._attr_current_option = restored_state
                else:
                    self._attr_current_option = restored_state
            else:
                # Если нет ни данных от устройства, ни сохраненного состояния, загружаем из сенсора (может быть значение по умолчанию)
                self._load_from_sensor()
        elif restored_state is not None:
            # Если нет данных от устройства, но есть сохраненное состояние, используем его
            self._internal_current_option = restored_state
            # Отображаем переведенное значение
            if self._option_translation_map and restored_state in self._option_translation_map.values():
                for translated, internal in self._option_translation_map.items():
                    if internal == restored_state:
                        self._attr_current_option = translated
                        break
                else:
                    self._attr_current_option = restored_state
            else:
                self._attr_current_option = restored_state
        else:
            # Если нет ни данных от устройства, ни сохраненного состояния, загружаем из сенсора
            self._load_from_sensor()
        
        # Обновляем видимость связанных select-сущностей при инициализации
        # Используем задержку, чтобы все entities успели зарегистрироваться
        if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
            async def delayed_update():
                await asyncio.sleep(0.5)  # Небольшая задержка для регистрации всех entities
                await self._update_related_entities_visibility()
            self.hass.async_create_task(delayed_update())
        
        # Подписываемся на события обновления устройства
        @callback
        def handle_device_update(event: Event) -> None:
            """Обработка обновления данных устройства."""
            if event.data.get("device_id") == self._device_id:
                # Определяем ключ сенсора для этого селекта
                sensor_key = None
                if self.entity_description.key == "channel_0_data_type":
                    sensor_key = "ctype0"
                elif self.entity_description.key == "channel_1_data_type":
                    sensor_key = "ctype1"
                elif self.entity_description.key == "channel_0_data_type_data":
                    sensor_key = "data_type0"
                elif self.entity_description.key == "channel_1_data_type_data":
                    sensor_key = "data_type1"
                elif self.entity_description.key == "channel_0_conversion_factor":
                    sensor_key = "f0"
                elif self.entity_description.key == "channel_1_conversion_factor":
                    sensor_key = "f1"
                
                # Получаем устройство
                device = self._device_manager.get_device(self._device_id)
                if device and device.data and sensor_key:
                    # Получаем новое значение из device.data
                    new_value = device.data.get(sensor_key)
                    # Преобразуем текущее внутреннее значение селекта в числовое значение
                    current_numeric_value = None
                    if self._internal_current_option:
                        current_numeric_value = self._convert_option_to_type(self._internal_current_option)
                    
                    # Сравниваем значения
                    try:
                        new_numeric_value = int(float(new_value)) if new_value is not None else None
                        # Если значение изменилось, обновляем селект
                        if new_numeric_value != current_numeric_value:
                            self._load_from_sensor()
                            self.async_write_ha_state()
                        # Если значение не изменилось, не обновляем селект (пользовательский выбор сохраняется)
                    except (ValueError, TypeError):
                        # Если не удалось сравнить, обновляем селект на всякий случай
                        self._load_from_sensor()
                        self.async_write_ha_state()
                else:
                    # Если нет данных или ключа, обновляем селект
                    self._load_from_sensor()
                    self.async_write_ha_state()
                # Обновление видимости связанных селектов происходит внутри _load_from_sensor()
                # для селектов channel_0_data_type и channel_1_data_type
        
        self.hass.bus.async_listen("waterius_device_update", handle_device_update)

    def _convert_type_to_option(self, type_value: Any) -> str:
        """Преобразование числового значения типа канала в строковую опцию."""
        try:
            type_int = int(float(type_value)) if type_value is not None else None
        except (ValueError, TypeError):
            # Для коэффициентов пересчета возвращаем "1" по умолчанию
            if self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
                return "1"
            return "NOT_USED"
        
        # Для коэффициентов пересчета (f0, f1)
        if self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
            if type_int is None:
                return "1"
            # Преобразуем числовое значение в строку, если оно есть в опциях
            option_str = str(type_int)
            if option_str in CONVERSION_FACTOR_OPTIONS:
                return option_str
            # Если значение не в списке опций, возвращаем ближайшее или "1" по умолчанию
            return "1"
        
        # Для data_type селектов
        if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            if type_int is None:
                internal_option = "OTHER"
            elif 0 <= type_int < len(DATA_TYPE_OPTIONS):
                internal_option = DATA_TYPE_OPTIONS[type_int]
            else:
                internal_option = "OTHER"
            
            # Если есть маппинг переводов, возвращаем переведенное значение
            if self._option_translation_map and internal_option:
                # Находим переведенное значение для внутреннего
                for translated, internal in self._option_translation_map.items():
                    if internal == internal_option:
                        return translated
                # Если не нашли, возвращаем внутреннее значение
                return internal_option
            
            return internal_option
        
        # Для ctype селектов
        internal_option = None
        if type_int == 0:
            internal_option = "MECHANIC"
        elif type_int == 2:
            internal_option = "ELECTRONIC"
        else:
            # Все остальные значения, включая 3 (HALL), преобразуются в NOT_USED
            internal_option = "NOT_USED"
        
        # Если есть маппинг переводов, возвращаем переведенное значение
        if self._option_translation_map and internal_option:
            # Находим переведенное значение для внутреннего
            for translated, internal in self._option_translation_map.items():
                if internal == internal_option:
                    return translated
            # Если не нашли, возвращаем внутреннее значение
            return internal_option
        
        return internal_option
    
    def _convert_option_to_type(self, option: str) -> int:
        """Преобразование строковой опции в числовое значение типа канала."""
        # Для коэффициентов пересчета (f0, f1)
        if self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
            try:
                return int(option)
            except (ValueError, TypeError):
                return 1  # Значение по умолчанию
        
        # Для data_type селектов
        if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            try:
                return DATA_TYPE_OPTIONS.index(option)
            except ValueError:
                return 6  # OTHER по умолчанию
        
        # Для ctype селектов
        if option == "MECHANIC":
            return 0
        elif option == "ELECTRONIC":
            return 2
        elif option == "HALL":
            return 3
        else:
            return -1  # NOT_USED или неизвестное значение
    
    def _load_from_sensor(self) -> None:
        """Загрузка значения из сенсора устройства."""
        device = self._device_manager.get_device(self._device_id)
        if not device or not device.data:
            # Устанавливаем значение по умолчанию в зависимости от типа селекта
            if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
                self._attr_current_option = "OTHER"
            else:
                self._attr_current_option = "NOT_USED"
            return
        
        # Определяем ключ сенсора в зависимости от типа select entity
        sensor_key = None
        if self.entity_description.key == "channel_0_data_type":
            sensor_key = "ctype0"
        elif self.entity_description.key == "channel_1_data_type":
            sensor_key = "ctype1"
        elif self.entity_description.key == "channel_0_data_type_data":
            sensor_key = "data_type0"
        elif self.entity_description.key == "channel_1_data_type_data":
            sensor_key = "data_type1"
        elif self.entity_description.key == "channel_0_conversion_factor":
            sensor_key = "f0"
        elif self.entity_description.key == "channel_1_conversion_factor":
            sensor_key = "f1"
        
        if sensor_key:
            type_value = device.data.get(sensor_key)
            internal_option = self._convert_type_to_option(type_value)
            # Сохраняем внутреннее значение
            self._internal_current_option = internal_option
            # Отображаем переведенное значение
            if self._option_translation_map and internal_option in self._option_translation_map.values():
                for translated, internal in self._option_translation_map.items():
                    if internal == internal_option:
                        self._attr_current_option = translated
                        break
                else:
                    self._attr_current_option = internal_option
            else:
                self._attr_current_option = internal_option
            
            # Обновляем видимость связанных селектов при автоматическом обновлении данных
            # для селектов channel_0_data_type и channel_1_data_type
            if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
                # Используем отложенную задачу для обновления видимости
                async def delayed_visibility_update():
                    await asyncio.sleep(0.1)  # Небольшая задержка для обновления состояния
                    await self._update_related_entities_visibility()
                self.hass.async_create_task(delayed_visibility_update())
        else:
            # Устанавливаем значение по умолчанию
            if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
                default_internal = "OTHER"
            elif self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
                default_internal = "1"
            else:
                default_internal = "NOT_USED"
            
            # Сохраняем внутреннее значение
            self._internal_current_option = default_internal
            # Отображаем переведенное значение
            if self._option_translation_map and default_internal in self._option_translation_map.values():
                for translated, internal in self._option_translation_map.items():
                    if internal == default_internal:
                        self._attr_current_option = translated
                        break
                else:
                    self._attr_current_option = default_internal
            else:
                self._attr_current_option = default_internal

    async def async_select_option(self, option: str) -> None:
        """Обработка выбора опции."""
        # Если это переведенное значение, конвертируем во внутреннее
        internal_option = option
        if self._option_translation_map and option in self._option_translation_map:
            internal_option = self._option_translation_map[option]
        
        # Проверяем опцию в зависимости от типа селекта (используем внутреннее значение)
        if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            if internal_option not in DATA_TYPE_OPTIONS:
                _LOGGER.warning("Неизвестная опция: %s", option)
                return
        elif self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
            if internal_option not in CONVERSION_FACTOR_OPTIONS:
                _LOGGER.warning("Неизвестная опция: %s", option)
                return
        else:
            if internal_option not in CHANNEL_TYPE_OPTIONS:
                _LOGGER.warning("Неизвестная опция: %s", option)
                return
        
        # Преобразуем опцию в числовое значение (используем внутреннее значение)
        type_value = self._convert_option_to_type(internal_option)
        
        # Определяем ключ сенсора в зависимости от типа select entity
        sensor_key = None
        if self.entity_description.key == "channel_0_data_type":
            sensor_key = "ctype0"
        elif self.entity_description.key == "channel_1_data_type":
            sensor_key = "ctype1"
        elif self.entity_description.key == "channel_0_data_type_data":
            sensor_key = "data_type0"
        elif self.entity_description.key == "channel_1_data_type_data":
            sensor_key = "data_type1"
        elif self.entity_description.key == "channel_0_conversion_factor":
            sensor_key = "f0"
        elif self.entity_description.key == "channel_1_conversion_factor":
            sensor_key = "f1"
        
        if not sensor_key:
            _LOGGER.warning("Неизвестный ключ select entity: %s", self.entity_description.key)
            return
        
        # Получаем устройство
        device = self._device_manager.get_device(self._device_id)
        if not device:
            _LOGGER.warning("Устройство %s не найдено", self._device_id)
            return
        
        # Обновляем данные устройства
        if device.data is None:
            device.data = {}
        
        # Сохраняем внутреннее значение для работы с данными ДО обновления device.data
        # Это нужно для правильной работы сравнения в handle_device_update
        self._internal_current_option = internal_option
        
        # Обновляем значение типа канала в данных устройства
        device.data[sensor_key] = type_value
        
        # Обновляем данные через device_manager, чтобы сенсор автоматически обновился
        self._device_manager.update_device_data(self._device_id, device.data)
        # Отображаем переведенное значение в интерфейсе
        if self._option_translation_map and internal_option in self._option_translation_map.values():
            # Находим переведенное значение для внутреннего
            for translated, internal in self._option_translation_map.items():
                if internal == internal_option:
                    self._attr_current_option = translated
                    break
            else:
                self._attr_current_option = internal_option
        else:
            self._attr_current_option = internal_option
        self.async_write_ha_state()
        
        # Обновляем видимость связанных select-сущностей при изменении типа счетчика
        # Используем небольшую задержку, чтобы убедиться, что состояние обновлено
        if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
            async def delayed_update():
                await asyncio.sleep(0.1)  # Небольшая задержка для обновления состояния
                await self._update_related_entities_visibility()
            self.hass.async_create_task(delayed_update())
        
        _LOGGER.info(
            "Обновлен тип канала %s для устройства %s: %s (значение: %d)",
            self.entity_description.key,
            self._device_name,
            option,
            type_value
        )
    
    async def _update_related_entities_visibility(self) -> None:
        """Обновление видимости связанных select-сущностей и сенсоров на основе типа счетчика."""
        # Определяем, какой канал (0 или 1) и соответствующие ключи
        data_type_key = None
        conversion_factor_key = None
        sensor_key = None
        if self.entity_description.key == "channel_0_data_type":
            data_type_key = "channel_0_data_type_data"
            conversion_factor_key = "channel_0_conversion_factor"
            sensor_key = "ch0"
        elif self.entity_description.key == "channel_1_data_type":
            data_type_key = "channel_1_data_type_data"
            conversion_factor_key = "channel_1_conversion_factor"
            sensor_key = "ch1"
        else:
            return
        
        # Получаем текущее значение типа счетчика
        # Используем внутреннее значение для проверки
        current_value = self._internal_current_option if hasattr(self, '_internal_current_option') and self._internal_current_option else self._attr_current_option
        # Если это переведенное значение, конвертируем во внутреннее
        if self._option_translation_map and current_value in self._option_translation_map:
            current_value = self._option_translation_map[current_value]
        
        should_hide = current_value == "NOT_USED"
        
        _LOGGER.info(
            "Обновление видимости для канала устройства %s: текущее значение=%s, should_hide=%s",
            self._device_name,
            current_value,
            should_hide
        )
        
        # Получаем entity registry
        registry = er.async_get(self.hass)
        
        # Формируем unique_id для связанных select-сущностей и сенсора
        data_type_unique_id = f"{self._device_id}_{data_type_key}"
        conversion_factor_unique_id = f"{self._device_id}_{conversion_factor_key}"
        sensor_unique_id = f"{self._device_id}_{sensor_key}"
        
        _LOGGER.debug(
            "Поиск entities: data_type_unique_id=%s, conversion_factor_unique_id=%s",
            data_type_unique_id,
            conversion_factor_unique_id
        )
        
        # Находим entities в registry по unique_id
        # Используем async_get_entity_id для поиска по unique_id
        data_type_entity_id = registry.async_get_entity_id("select", DOMAIN, data_type_unique_id)
        conversion_factor_entity_id = registry.async_get_entity_id("select", DOMAIN, conversion_factor_unique_id)
        sensor_entity_id = registry.async_get_entity_id("sensor", DOMAIN, sensor_unique_id)
        
        data_type_entry = None
        conversion_factor_entry = None
        sensor_entry = None
        
        if data_type_entity_id:
            entry = registry.async_get(data_type_entity_id)
            if entry:
                data_type_entry = (data_type_entity_id, entry)
                _LOGGER.debug("Найден data_type entity: %s, disabled_by=%s", data_type_entity_id, entry.disabled_by)
        
        if conversion_factor_entity_id:
            entry = registry.async_get(conversion_factor_entity_id)
            if entry:
                conversion_factor_entry = (conversion_factor_entity_id, entry)
                _LOGGER.debug("Найден conversion_factor entity: %s, disabled_by=%s", conversion_factor_entity_id, entry.disabled_by)
        
        if sensor_entity_id:
            entry = registry.async_get(sensor_entity_id)
            if entry:
                sensor_entry = (sensor_entity_id, entry)
                _LOGGER.debug("Найден sensor entity: %s, disabled_by=%s", sensor_entity_id, entry.disabled_by)
        
        # Обновляем видимость для типа данных
        if data_type_entry:
            entity_id, entry = data_type_entry
            if should_hide:
                # Скрываем entity
                if entry.disabled_by is None:
                    registry.async_update_entity(
                        entity_id,
                        disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )
                    _LOGGER.info("Скрыт select для типа данных канала устройства %s", self._device_name)
                else:
                    _LOGGER.debug("Select для типа данных уже скрыт (disabled_by=%s)", entry.disabled_by)
            else:
                # Показываем entity (проверяем любую причину скрытия интеграцией)
                if entry.disabled_by is not None:
                    registry.async_update_entity(
                        entity_id,
                        disabled_by=None
                    )
                    _LOGGER.info("Показан select для типа данных канала устройства %s (было disabled_by=%s)", 
                                self._device_name, entry.disabled_by)
                else:
                    _LOGGER.debug("Select для типа данных уже показан")
        else:
            _LOGGER.warning("Не найден data_type entity для устройства %s", self._device_name)
        
        # Обновляем видимость для коэффициента пересчета
        if conversion_factor_entry:
            entity_id, entry = conversion_factor_entry
            if should_hide:
                # Скрываем entity
                if entry.disabled_by is None:
                    registry.async_update_entity(
                        entity_id,
                        disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )
                    _LOGGER.info("Скрыт select для коэффициента пересчета канала устройства %s", self._device_name)
                else:
                    _LOGGER.debug("Select для коэффициента пересчета уже скрыт (disabled_by=%s)", entry.disabled_by)
            else:
                # Показываем entity (проверяем любую причину скрытия интеграцией)
                if entry.disabled_by is not None:
                    registry.async_update_entity(
                        entity_id,
                        disabled_by=None
                    )
                    _LOGGER.info("Показан select для коэффициента пересчета канала устройства %s (было disabled_by=%s)", 
                                self._device_name, entry.disabled_by)
                else:
                    _LOGGER.debug("Select для коэффициента пересчета уже показан")
        else:
            _LOGGER.warning("Не найден conversion_factor entity для устройства %s", self._device_name)
        
        # Обновляем видимость для сенсора канала
        if sensor_entry:
            entity_id, entry = sensor_entry
            if should_hide:
                # Скрываем entity
                if entry.disabled_by is None:
                    registry.async_update_entity(
                        entity_id,
                        disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )
                    _LOGGER.info("Скрыт sensor для канала устройства %s", self._device_name)
                else:
                    _LOGGER.debug("Sensor для канала уже скрыт (disabled_by=%s)", entry.disabled_by)
            else:
                # Показываем entity (проверяем любую причину скрытия интеграцией)
                if entry.disabled_by is not None:
                    registry.async_update_entity(
                        entity_id,
                        disabled_by=None
                    )
                    _LOGGER.info("Показан sensor для канала устройства %s (было disabled_by=%s)", 
                                self._device_name, entry.disabled_by)
                else:
                    _LOGGER.debug("Sensor для канала уже показан")
        else:
            _LOGGER.warning("Не найден sensor entity для канала устройства %s", self._device_name)

