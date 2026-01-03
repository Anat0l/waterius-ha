"""Вспомогательные функции для интеграции Waterius."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DEVICE_MANUFACTURER, DEVICE_MODEL, DEVICE_HW_VERSION

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .device_manager import DeviceManager


def get_device_identifiers(device_id: str, device_mac: str | None = None) -> set[tuple[str, str]]:
    """Получение идентификаторов устройства для DeviceInfo.
    
    Args:
        device_id: ID устройства
        device_mac: MAC адрес устройства (опционально)
        
    Returns:
        Множество кортежей (domain, identifier) для DeviceInfo
    """
    identifiers = {(DOMAIN, device_id)}
    if device_mac:
        identifiers.add((DOMAIN, device_mac))
    return identifiers


def get_software_version(device_data: dict[str, Any] | None) -> str | None:
    """Формирование версии ПО из данных устройства.
    
    Args:
        device_data: Словарь с данными устройства
        
    Returns:
        Строка с версией ПО или None, если версия недоступна
    """
    if not device_data:
        return None
    
    version_esp = device_data.get("version_esp")
    version = device_data.get("version")
    
    if version_esp is not None and version is not None:
        return f"{version_esp}.{version}"
    
    if version_esp is not None:
        return str(version_esp)
    
    if version is not None:
        return str(version)
    
    return None


def get_configuration_url(ip_address: str | None) -> str | None:
    """Формирование URL конфигурации устройства.
    
    Args:
        ip_address: IP адрес устройства
        
    Returns:
        URL конфигурации или None, если IP адрес недоступен
    """
    if ip_address:
        return f"http://{ip_address}"
    return None


def get_device_info(
    device_manager: DeviceManager,
    device_id: str,
    device_name: str,
    device_mac: str | None = None,
    device_data: dict[str, Any] | None = None,
) -> DeviceInfo:
    """Получение информации об устройстве для DeviceInfo.
    
    Args:
        device_manager: Менеджер устройств
        device_id: ID устройства
        device_name: Имя устройства
        device_mac: MAC адрес устройства (опционально)
        device_data: Данные устройства (опционально, если None, будет получено из device_manager)
        
    Returns:
        DeviceInfo объект с информацией об устройстве
    """
    identifiers = get_device_identifiers(device_id, device_mac)
    
    # Если device_data не передан, получаем из device_manager
    if device_data is None:
        device = device_manager.get_device(device_id)
        device_data = device.data if device else None
    
    # Базовая информация об устройстве (всегда присутствует)
    device_info = DeviceInfo(
        identifiers=identifiers,
        name=device_name,
        manufacturer=DEVICE_MANUFACTURER,
        model=DEVICE_MODEL,
        hw_version=DEVICE_HW_VERSION,
    )
    
    # Дополнительная информация (только если есть данные)
    # Не включаем поля с None, чтобы не затереть существующие значения
    if device_data:
        sw_version = get_software_version(device_data)
        if sw_version is not None:
            device_info["sw_version"] = sw_version
        
        serial_number = device_data.get("key")
        if serial_number is not None:
            device_info["serial_number"] = serial_number
        
        ip_address = device_data.get("ip")
        configuration_url = get_configuration_url(ip_address)
        if configuration_url is not None:
            device_info["configuration_url"] = configuration_url
    
    return device_info


@callback
def setup_device_added_listener(
    hass: HomeAssistant,
    entry_id: str,
    device_manager: "DeviceManager",
    async_add_entities: AddEntitiesCallback,
    entity_factory: Callable[..., Any],  # Функция для создания entity с переменными аргументами
    entity_descriptions: list[Any],
    platform_name: str,
) -> None:
    """Настройка подписки на события добавления новых устройств.
    
    Args:
        hass: Экземпляр Home Assistant
        entry_id: ID config entry
        device_manager: Менеджер устройств
        async_add_entities: Callback для добавления entities
        entity_factory: Функция для создания entity (например, WateriusSensor)
        entity_descriptions: Список описаний entities (например, SENSOR_DESCRIPTIONS)
        platform_name: Имя платформы для логирования (например, "sensor")
    """
    @callback
    def handle_device_added(event: Event) -> None:
        """Обработка добавления нового устройства."""
        _LOGGER.debug(
            "🔔 [%s] Получено событие waterius_device_added: device_id=%s, entry_id=%s (ожидаемый entry_id=%s)",
            platform_name,
            event.data.get("device_id"),
            event.data.get("entry_id"),
            entry_id
        )
        
        if event.data.get("entry_id") != entry_id:
            _LOGGER.debug(
                "[%s] Пропускаем событие - entry_id не совпадает",
                platform_name
            )
            return
        
        device_id = event.data.get("device_id")
        device_name = event.data.get("device_name")
        device_mac = event.data.get("device_mac")
        
        if not device_id or not device_name:
            _LOGGER.debug(
                "[%s] Пропускаем событие - отсутствует device_id или device_name",
                platform_name
            )
            return
        
        _LOGGER.debug(
            "📦 [%s] Создаем entities для устройства %s (%s)...",
            platform_name,
            device_name,
            device_id
        )
        
        # Создаем entities для нового устройства
        new_entities = []
        for description in entity_descriptions:
            try:
                # entity_factory может принимать разное количество аргументов
                # в зависимости от платформы (sensor, select, number)
                entity = entity_factory(
                    device_manager,
                    device_id,
                    device_name,
                    device_mac,
                    description,
                )
                new_entities.append(entity)
                _LOGGER.debug(
                    "[%s] Создан entity: %s",
                    platform_name,
                    description.key if hasattr(description, 'key') else str(description)
                )
            except Exception as e:
                _LOGGER.error(
                    "Ошибка при создании %s entity для устройства %s (description=%s): %s",
                    platform_name,
                    device_name,
                    description.key if hasattr(description, 'key') else str(description),
                    e,
                    exc_info=True
                )
        
        _LOGGER.debug(
            "✅ [%s] Добавляем %d entities в Home Assistant для устройства %s...",
            platform_name,
            len(new_entities),
            device_name
        )
        async_add_entities(new_entities, update_before_add=True)
        _LOGGER.debug("Созданы %s entities для устройства %s", platform_name, device_name)
    
    hass.bus.async_listen("waterius_device_added", handle_device_added)



