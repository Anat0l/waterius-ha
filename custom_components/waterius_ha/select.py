"""Select platform для интеграции Waterius."""
from __future__ import annotations

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
    CHANNEL_TYPE_OPTIONS,
    CHANNEL_TYPE_NOT_USED,
    CHANNEL_TYPE_MECHANIC,
    CHANNEL_TYPE_ELECTRONIC,
    COUNTER_NAME_OPTIONS,  # Для cname0/cname1
    COUNTER_NAME_OTHER,
    CONVERSION_FACTOR_OPTIONS,
)
from .device_manager import DeviceManager
from .entity import WateriusEntity
from .helpers import get_device_info, setup_device_added_listener
from . import WateriusConfigEntry

_LOGGER = logging.getLogger(__name__)

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
    entry: WateriusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка select платформы."""
    if entry.runtime_data is None:
        _LOGGER.error("Runtime data не инициализирована для entry %s", entry.entry_id)
        return

    device_manager: DeviceManager = entry.runtime_data.device_manager

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
    setup_device_added_listener(
        hass,
        entry.entry_id,
        device_manager,
        async_add_entities,
        lambda dm, did, dn, dmac, desc: WateriusSelect(dm, did, dn, dmac, desc, entry),
        SELECT_DESCRIPTIONS,
        "select",
    )


class WateriusSelect(WateriusEntity, SelectEntity, RestoreEntity):
    """Представление select для типа канала устройства Waterius.
    
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
        description: SelectEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Инициализация select."""
        super().__init__(device_manager, device_id, device_name, device_mac)
        self._base_description = description
        self._attr_unique_id = f"{device_id}_{description.key}_config"
        self._attr_has_entity_name = True
        self._entry = entry
        # Определяем опции в зависимости от типа select entity
        if description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            self._attr_options = COUNTER_NAME_OPTIONS  # ⚡ ИЗМЕНЕНО: было DATA_TYPE_OPTIONS, теперь COUNTER_NAME для cname
        elif description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
            self._attr_options = CONVERSION_FACTOR_OPTIONS
        else:
            # Для channel_0_data_type и channel_1_data_type опции будут переведены в async_added_to_hass
            self._attr_options = CHANNEL_TYPE_OPTIONS
        self._attr_current_option: str | None = None
        self._option_translation_map: dict[str, str] = {}  # Маппинг между переведенными и внутренними значениями
        self._reverse_translation_map: dict[str, str] = {}  # Обратный маппинг для быстрого поиска
        self._internal_current_option: str | None = None  # Внутреннее значение для работы с данными

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
    def entity_description(self) -> SelectEntityDescription:
        """Описание entity."""
        return self._base_description
    
    @property
    def _select_type(self) -> str:
        """Определяет тип select entity для упрощения логики.
        
        Returns:
            'counter_type' - для channel_X_data_type (ctype0/1)
            'data_type_data' - для channel_X_data_type_data (cname0/1)
            'conversion_factor' - для channel_X_conversion_factor (f0/1)
            'unknown' - для неизвестных типов
        """
        key = self.entity_description.key
        if "data_type_data" in key:
            return "data_type_data"
        elif "conversion_factor" in key:
            return "conversion_factor"
        elif "data_type" in key:  # Но не data_type_data
            return "counter_type"
        return "unknown"
    
    @property
    def _channel_number(self) -> int | None:
        """Определяет номер канала для entity.
        
        Returns:
            0 - для канала 0
            1 - для канала 1
            None - если entity не связан с каналом
        """
        key = self.entity_description.key
        if "channel_0" in key:
            return 0
        elif "channel_1" in key:
            return 1
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Дополнительные атрибуты state - включая внутреннее значение для синхронизации."""
        attrs: dict[str, Any] = {}
        
        # Для select с переводами добавляем internal_value
        if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
            # Для типа канала: сохраняем внутреннюю опцию и её числовое значение
            if self._attr_current_option:
                from .const import convert_channel_type_to_value
                attrs["internal_option"] = self._attr_current_option
                attrs["internal_value"] = convert_channel_type_to_value(self._attr_current_option)
        
        elif self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            # Для cname (CounterName): сохраняем внутреннюю опцию и её числовое значение
            if self._attr_current_option:
                from .const import convert_counter_name_to_value  # ⚡ ИЗМЕНЕНО: было convert_data_type_to_value
                attrs["internal_option"] = self._attr_current_option
                attrs["internal_value"] = convert_counter_name_to_value(self._attr_current_option)
        
        return attrs

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
            else:  # channel_0_data_type_data, channel_1_data_type_data
                options_to_translate = COUNTER_NAME_OPTIONS  # ⚡ ИСПРАВЛЕНО: было DATA_TYPE_OPTIONS
            
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
            # Создаем обратный маппинг для быстрого поиска
            self._reverse_translation_map = {v: k for k, v in reverse_map.items()}
        
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
                    "Восстановлено сохраненное состояние для %s устройства %s: %s",
                    self.entity_description.key,
                    self._device_name,
                    restored_state
                )
        
        # Определяем финальное значение
        # ВАЖНЫЙ ПРИОРИТЕТ (от высшего к низшему):
        # 1. Данные от РЕАЛЬНОГО устройства (device.data с last_update_time)
        # 2. Сохраненное состояние (RestoreEntity) - пользовательские настройки
        # 3. Значения по умолчанию (device.data без last_update_time)
        
        device = self._device_manager.get_device(self._device_id)
        sensor_key = self._get_sensor_key()
        
        # 🔍 ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ для отладки
        _LOGGER.debug(
            "[%s] Инициализация для устройства %s: sensor_key=%s, device_exists=%s, has_last_update=%s, restored_state=%s",
            self.entity_description.key,
            self._device_name,
            sensor_key,
            device is not None,
            device.last_update_time if device else None,
            restored_state
        )
        
        # Проверяем, есть ли данные от устройства в device.data
        # Если sensor_key присутствует в device.data, значит данные уже получены
        # (либо от устройства при первом обновлении, либо восстановлены из сохраненного состояния)
        has_device_data = (
            device and 
            device.data and 
            sensor_key and 
            sensor_key in device.data
        )
        
        # Проверяем, это данные от реального устройства или из сохраненного состояния
        # last_update_time устанавливается только когда устройство отправляет данные
        has_real_device_data = has_device_data and device is not None and device.last_update_time is not None
        
        if has_real_device_data and device is not None and sensor_key is not None:
            # ПРИОРИТЕТ 1: Реальные данные от устройства (с подтвержденным last_update_time)
            raw_value = device.data.get(sensor_key)
            sensor_value = self._convert_type_to_option(raw_value)
            self._set_current_option(sensor_value)
            _LOGGER.debug(
                "[%s] Использованы реальные данные устройства %s: %s=%s → %s",
                self.entity_description.key,
                self._device_name,
                sensor_key,
                raw_value,
                sensor_value
            )
        elif restored_state is not None:
            # ПРИОРИТЕТ 2: Сохраненное состояние (если нет данных от устройства)
            self._set_current_option(restored_state)
            _LOGGER.debug(
                "[%s] Использовано сохраненное состояние для устройства %s: %s",
                self.entity_description.key,
                self._device_name,
                restored_state
            )
            
            # Обновляем device.data согласно сохраненному состоянию
            # НО НЕ устанавливаем last_update_time, чтобы при следующем обновлении
            # от устройства данные корректно применились
            if device and device.data and sensor_key:
                type_value = self._convert_option_to_type(restored_state)
                device.data[sensor_key] = type_value
                _LOGGER.debug(
                    "[%s] Синхронизация device.data[%s] = %s (восстановлено из RestoreEntity)",
                    self.entity_description.key,
                    sensor_key,
                    type_value
                )
        elif has_device_data and device is not None and sensor_key is not None:
            # ПРИОРИТЕТ 3: Данные из device.data (первое обновление от устройства)
            # Используется когда:
            # - Нет last_update_time (еще не установлен при первом создании entities)
            # - Нет сохраненного состояния (новое устройство)
            # - Но device.data уже заполнен данными от устройства
            raw_value = device.data.get(sensor_key)
            sensor_value = self._convert_type_to_option(raw_value)
            self._set_current_option(sensor_value)
            _LOGGER.debug(
                "[%s] Использованы данные из device.data для устройства %s: %s=%s → %s",
                self.entity_description.key,
                self._device_name,
                sensor_key,
                raw_value,
                sensor_value
            )
        else:
            # ПРИОРИТЕТ 4: Fallback - для НОВЫХ устройств без данных
            # Для типа счетчика (ctype) используем NOT_USED (255), чтобы скрыть связанные entities
            # Для остальных select'ов загружаем из _load_from_sensor
            if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
                # Для типа счетчика: используем NOT_USED для новых устройств
                self._set_current_option("not_used")
                _LOGGER.debug(
                    "[%s] Fallback для нового устройства %s: установлен в 'NOT_USED'",
                    self.entity_description.key,
                    self._device_name
                )
            else:
                # Для других select'ов: загрузка из _load_from_sensor
                self._load_from_sensor()
                _LOGGER.debug(
                    "[%s] Fallback для устройства %s: загрузка из _load_from_sensor",
                    self.entity_description.key,
                    self._device_name
                )
        
        # Обновляем видимость связанных select-сущностей при инициализации
        # Используем событие entity_registry_updated вместо sleep
        if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
            @callback
            def handle_entity_registry_updated_for_visibility(event: Event) -> None:
                """Обработка обновления entity registry для обновления видимости."""
                if event.data.get("action") != "create":
                    return
                # Проверяем, что это наш entity
                entity_id = event.data.get("entity_id")
                if not entity_id:
                    return
                registry = er.async_get(self.hass)
                entry = registry.async_get(entity_id)
                if entry and entry.unique_id == self._attr_unique_id:
                    # Обновляем видимость связанных entities
                    self.hass.async_create_task(self._update_related_entities_visibility())
                    # Отменяем подписку после успешного обновления
                    if hasattr(self, "_unsub_entity_registry_visibility"):
                        self._unsub_entity_registry_visibility()
                        self._unsub_entity_registry_visibility = None
            
            # Подписываемся на событие обновления entity registry
            self._unsub_entity_registry_visibility = self.hass.bus.async_listen(
                "entity_registry_updated",
                handle_entity_registry_updated_for_visibility,
            )
            
            # Также пытаемся обновить сразу, если entity уже зарегистрирован
            registry = er.async_get(self.hass)
            entity_id = registry.async_get_entity_id("select", DOMAIN, self._attr_unique_id)
            if entity_id:
                self.hass.async_create_task(self._update_related_entities_visibility())
                if hasattr(self, "_unsub_entity_registry_visibility") and self._unsub_entity_registry_visibility:
                    self._unsub_entity_registry_visibility()
                    self._unsub_entity_registry_visibility = None
        
        # Подписываемся на события обновления устройства
        @callback
        def handle_device_update(event: Event) -> None:
            """Обработка обновления данных устройства.
            
            ✅ НОВАЯ АРХИТЕКТУРА: Select НЕ обновляется от устройства!
            Select хранит ЖЕЛАЕМОЕ значение (что хочет пользователь).
            Sensor хранит ТЕКУЩЕЕ значение (что реально на устройстве).
            Select обновляется ТОЛЬКО при изменении пользователем!
            
            Подписка на события сохранена для архитектурной симметрии
            и возможного будущего функционала.
            """
            return
        
        # Сохраняем подписку для корректной очистки при удалении entity
        self._unsub_update = self.hass.bus.async_listen(
            "waterius_device_update", handle_device_update
        )

    def _convert_type_to_option(self, type_value: Any) -> str:
        """Преобразование числового значения типа канала в строковую опцию."""
        try:
            type_int = int(float(type_value)) if type_value is not None else None
        except (ValueError, TypeError):
            # Для коэффициентов пересчета возвращаем "1" по умолчанию
            if self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
                return "1"
            return "not_used"
        
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
        
        # Для cname селектов (CounterName)
        if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            from .const import convert_value_to_counter_name  # ⚡ ИЗМЕНЕНО: было convert_value_to_data_type
            
            # Используем helper функцию для преобразования
            internal_option = convert_value_to_counter_name(type_int)
            
            # Если есть маппинг переводов, возвращаем переведенное значение
            if self._reverse_translation_map and internal_option in self._reverse_translation_map:
                return self._reverse_translation_map[internal_option]
            return internal_option
        
        # Для ctype селектов
        # ⚡ Согласно протоколу устройства: DISCRETE=0 (Механический), ELECTRONIC=2, NONE=255
        internal_option: str = "not_used"  # Значение по умолчанию
        if type_int == 0:  # ⚡ ИСПРАВЛЕНО: было 1, теперь 0
            internal_option = "mechanic"  # DISCRETE в прошивке = Механический
        elif type_int == 2:
            internal_option = "electronic"
        elif type_int == 255:
            internal_option = "not_used"
        else:
            # Неизвестные значения (0=NAMUR, 3=HALL и др.) преобразуются в not_used
            _LOGGER.debug("Неизвестное значение типа счетчика: %s, используется not_used", type_int)
            internal_option = "not_used"
        
        # Если есть маппинг переводов, возвращаем переведенное значение
        if self._reverse_translation_map and internal_option in self._reverse_translation_map:
            return self._reverse_translation_map[internal_option]
        return internal_option
    
    def _convert_option_to_type(self, option: str) -> int:
        """Преобразование строковой опции в числовое значение типа канала."""
        # Для коэффициентов пересчета (f0, f1)
        if self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor"):
            try:
                return int(option)
            except (ValueError, TypeError):
                return 1  # Значение по умолчанию
        
        # Для cname селектов (CounterName)
        if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
            from .const import convert_counter_name_to_value  # ⚡ ИЗМЕНЕНО: было convert_data_type_to_value
            return convert_counter_name_to_value(option)
        
        # Для ctype селектов
        # ⚡ Согласно протоколу устройства: DISCRETE=0 (Механический), ELECTRONIC=2, NONE=255
        if option == "mechanic":
            return CHANNEL_TYPE_MECHANIC  # 0 (DISCRETE в прошивке) ⚡ ИСПРАВЛЕНО
        elif option == "electronic":
            return CHANNEL_TYPE_ELECTRONIC  # 2
        else:  # not_used и любые другие
            return CHANNEL_TYPE_NOT_USED  # 255
    
    def _get_sensor_key(self) -> str | None:
        """Получение ключа сенсора для текущего select entity."""
        key_mapping = {
            "channel_0_data_type": "ctype0",
            "channel_1_data_type": "ctype1",
            "channel_0_data_type_data": "cname0",  # ⚡ ИЗМЕНЕНО: было data_type0
            "channel_1_data_type_data": "cname1",  # ⚡ ИЗМЕНЕНО: было data_type1
            "channel_0_conversion_factor": "f0",
            "channel_1_conversion_factor": "f1",
        }
        return key_mapping.get(self.entity_description.key)
    
    def _set_current_option(self, internal_option: str) -> None:
        """Установка текущей опции с учетом переводов."""
        self._internal_current_option = internal_option
        # Отображаем переведенное значение, если есть маппинг
        if self._reverse_translation_map:
            self._attr_current_option = self._reverse_translation_map.get(internal_option, internal_option)
        else:
            self._attr_current_option = internal_option

    def _load_from_sensor(self) -> None:
        """Загрузка значения из сенсора устройства."""
        device = self._device_manager.get_device(self._device_id)
        if not device or not device.data:
            # Устанавливаем значение по умолчанию в зависимости от типа селекта
            if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
                self._attr_current_option = "other"
            else:
                self._attr_current_option = "not_used"
            return
        
        sensor_key = self._get_sensor_key()
        
        if sensor_key:
            type_value = device.data.get(sensor_key)
            internal_option = self._convert_type_to_option(type_value)
            self._set_current_option(internal_option)
            
            # Обновляем видимость связанных селектов при автоматическом обновлении данных
            # для селектов channel_0_data_type и channel_1_data_type
            if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
                # Вызываем обновление видимости напрямую без задержек
                self.hass.async_create_task(self._update_related_entities_visibility())
        else:
            # Устанавливаем значение по умолчанию
            default_internal = (
                "other" if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data")
                else "1" if self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor")
                else "not_used"
            )
            self._set_current_option(default_internal)

    async def async_select_option(self, option: str) -> None:
        """Обработка выбора опции."""
        try:
            # Если это переведенное значение, конвертируем во внутреннее
            internal_option = option
            if self._option_translation_map and option in self._option_translation_map:
                internal_option = self._option_translation_map[option]
            
            # Проверяем опцию в зависимости от типа селекта
            valid_options = (
                COUNTER_NAME_OPTIONS if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data")  # ⚡ ИЗМЕНЕНО: было DATA_TYPE_OPTIONS
                else CONVERSION_FACTOR_OPTIONS if self.entity_description.key in ("channel_0_conversion_factor", "channel_1_conversion_factor")
                else CHANNEL_TYPE_OPTIONS
            )
            if internal_option not in valid_options:
                _LOGGER.warning("Неизвестная опция %s для %s", option, self.entity_description.key)
                return
            
            # Преобразуем опцию в числовое значение (используем внутреннее значение)
            type_value = self._convert_option_to_type(internal_option)
            
            sensor_key = self._get_sensor_key()
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
            
            # ✅ НОВАЯ АРХИТЕКТУРА: Select НЕ обновляет device.data!
            # Select хранит ЖЕЛАЕМОЕ значение (что хочет пользователь)
            # device.data хранит ТЕКУЩЕЕ значение (что реально на устройстве)
            # Это позволяет видеть разницу через config_sync!
            
            _LOGGER.info(
                "[%s] 👤 ПОЛЬЗОВАТЕЛЬ изменил %s устройства %s: %s → %s (числовое: %d)",
                self.entity_description.key,
                self.entity_description.key,
                self._device_name,
                self._internal_current_option,
                internal_option,
                type_value
            )
            
            # Отображаем переведенное значение в интерфейсе
            self._set_current_option(internal_option)
            
            # Сохраняем состояние в Home Assistant
            self.async_write_ha_state()
            
            _LOGGER.debug(
                "[%s] Состояние сохранено в HA через async_write_ha_state()",
                self.entity_description.key
            )
            
            # Обновляем видимость связанных select-сущностей при изменении типа счетчика
            # ВАЖНО: Обновление видимости только для channel_X_data_type (тип счетчика)
            # Для других select'ов (data_type_data, conversion_factor) перезагрузка НЕ нужна
            if self.entity_description.key in ("channel_0_data_type", "channel_1_data_type"):
                # Вызываем обновление видимости напрямую без задержек
                self.hass.async_create_task(self._update_related_entities_visibility())
            
            # ⚡ ВАЖНО: Принудительно обновляем сенсор счетчика при изменении data_type
            # Сенсор читает data_type из SELECT, поэтому нужно обновить его device_class и unit
            if self.entity_description.key in ("channel_0_data_type_data", "channel_1_data_type_data"):
                # Определяем канал
                channel = 0 if self.entity_description.key == "channel_0_data_type_data" else 1
                
                # Отправляем событие обновления для принудительного пересчета device_class и unit
                # State уже обновлён (async_write_ha_state выше), поэтому задержка не нужна
                self.hass.bus.async_fire(
                    "waterius_device_update",
                    {
                        "device_id": self._device_id,
                        "device_name": self._device_name,
                        "source": "data_type_change",
                        "changed_channel": channel,
                    },
                )
                _LOGGER.info(
                    "[%s] 🔄 Отправлено событие для обновления device_class/unit сенсора ch%d",
                    self.entity_description.key,
                    channel
                )
            
            _LOGGER.info(
                "✅ Обновлен тип канала %s для устройства %s: %s (значение: %d)",
                self.entity_description.key,
                self._device_name,
                option,
                type_value
            )
        except Exception as e:
            _LOGGER.error(
                "Ошибка при обновлении select %s для устройства %s: %s",
                self.entity_description.key,
                self._device_name,
                e
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
        current_value = self._internal_current_option or self._attr_current_option
        # Если это переведенное значение, конвертируем во внутреннее
        if self._option_translation_map and current_value in self._option_translation_map:
            current_value = self._option_translation_map[current_value]
        
        should_hide = current_value == "not_used"
        
        _LOGGER.debug(
            "Обновление видимости для канала устройства %s: текущее значение=%s, should_hide=%s",
            self._device_name,
            current_value,
            should_hide
        )
        
        # Получаем entity registry один раз
        registry = er.async_get(self.hass)
        
        # Формируем unique_id для связанных select-сущностей и сенсора
        # Для select entities добавляем суффикс "_config" (см. __init__)
        data_type_unique_id = f"{self._device_id}_{data_type_key}_config"
        conversion_factor_unique_id = f"{self._device_id}_{conversion_factor_key}_config"
        sensor_unique_id = f"{self._device_id}_{sensor_key}"
        
        # Находим entities в registry по unique_id (оптимизировано - один вызов для каждого типа)
        def get_entity_entry(platform: str, unique_id: str) -> tuple[str, er.RegistryEntry] | None:
            """Получение entity entry из registry по unique_id.
            
            Args:
                platform: Платформа entity (например, 'select', 'sensor')
                unique_id: Уникальный ID entity
                
            Returns:
                Кортеж (entity_id, entry) или None если не найдено
            """
            entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
            if not entity_id:
                return None
            entry = registry.async_get(entity_id)
            return (entity_id, entry) if entry else None
        
        # Получаем все entries одним проходом
        data_type_entry = get_entity_entry("select", data_type_unique_id)
        conversion_factor_entry = get_entity_entry("select", conversion_factor_unique_id)
        sensor_entry = get_entity_entry("sensor", sensor_unique_id)
        
        # Флаг для отслеживания изменений
        visibility_changed = False
        
        # Вспомогательная функция для обновления видимости entity
        def update_entity_visibility(entry_tuple: tuple[str, er.RegistryEntry] | None, entity_type: str) -> bool:
            """Обновление видимости entity.
            
            Returns:
                True если видимость была изменена, False иначе
            """
            if not entry_tuple:
                # Это нормальная ситуация при автоматическом добавлении устройства,
                # когда entities создаются асинхронно и могут еще не быть зарегистрированы
                _LOGGER.debug("Не найден %s entity для канала устройства %s (возможно, еще не создан)", entity_type, self._device_name)
                return False
            
            entity_id, entry = entry_tuple
            changed = False
            
            if should_hide:
                # Скрываем entity, когда тип счетчика = "not_used"
                # Это ЯВНОЕ намерение пользователя - канал не используется
                if entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                    # Уже скрыта интеграцией - ничего не меняем
                    _LOGGER.debug("%s для канала уже скрыт интеграцией", entity_type)
                elif entry.disabled_by is None:
                    # Entity включена - скрываем, так как пользователь явно выбрал "Не используется"
                    registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
                    _LOGGER.debug(
                        "Скрыт %s для канала устройства %s (тип счетчика = 'Не используется')",
                        entity_type, self._device_name
                    )
                    changed = True
                elif entry.disabled_by == er.RegistryEntryDisabler.USER:
                    # Отключена пользователем вручную - оставляем как есть, не меняем disabled_by
                    # Пользователь сам отключил, значит хочет, чтобы была отключена
                    _LOGGER.debug("%s для канала уже скрыт пользователем вручную", entity_type)
                else:
                    # Отключена другим способом - не трогаем
                    _LOGGER.debug("%s для канала уже скрыт (disabled_by=%s)", entity_type, entry.disabled_by)
            else:
                # Показываем entity ТОЛЬКО если она была отключена интеграцией
                if entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                    registry.async_update_entity(entity_id, disabled_by=None)
                    _LOGGER.debug("Показан %s для канала устройства %s", entity_type, self._device_name)
                    changed = True
                elif entry.disabled_by is None:
                    _LOGGER.debug("%s для канала уже показан", entity_type)
                else:
                    # Отключена пользователем или другим способом - не трогаем
                    _LOGGER.debug("%s для канала отключен (disabled_by=%s), не меняем", entity_type, entry.disabled_by)
            
            return changed
        
        # Обновляем видимость для всех связанных entities
        if update_entity_visibility(data_type_entry, "select для типа данных"):
            visibility_changed = True
        if update_entity_visibility(conversion_factor_entry, "select для коэффициента пересчета"):
            visibility_changed = True
        if update_entity_visibility(sensor_entry, "sensor"):
            visibility_changed = True
        
        # Если видимость изменилась, перезагружаем config entry для немедленной активации
        if visibility_changed:
            _LOGGER.info(
                "Видимость entities изменена для устройства %s. "
                "Перезагрузка интеграции для немедленной активации...",
                self._device_name
            )
            
            # 🚀 МГНОВЕННАЯ АКТИВАЦИЯ: Перезагружаем config entry
            # Это единственный надежный способ активировать/деактивировать entities немедленно
            if self._entry:
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._entry.entry_id)
                )
                _LOGGER.debug(
                    "🔄 Запущена перезагрузка config entry %s для немедленной активации entities",
                    self._entry.entry_id
                )

