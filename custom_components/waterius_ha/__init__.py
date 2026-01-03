"""Интеграция Waterius для Home Assistant."""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MAC,
    CONF_DEVICE_KEY,
)
from .exceptions import ZeroconfAddressError, ZeroconfConversionError

if TYPE_CHECKING:
    from .device_manager import DeviceManager
    from .web_server import WateriusWebServer

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER, Platform.SWITCH]


@dataclass
class WateriusRuntimeData:
    """Данные времени выполнения для интеграции Waterius."""
    web_server: "WateriusWebServer"
    device_manager: "DeviceManager"
    zeroconf_service_info: Any | None = field(default=None)  # ServiceInfo для Zeroconf (для повторной регистрации)
    zeroconf_registered: bool = field(default=False)  # Флаг успешной регистрации Zeroconf
    ha_hostname: str | None = field(default=None)  # Hostname из настроек Home Assistant (если есть)


WateriusConfigEntry: TypeAlias = ConfigEntry[WateriusRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: WateriusConfigEntry) -> bool:
    """Инициализация интеграции из config entry."""
    from .device_manager import DeviceManager
    from .web_server import WateriusWebServer
    
    # Обновляем title если это старая версия с упоминанием порта
    if entry.title and ("порт" in entry.title.lower() or "port" in entry.title.lower()):
        hass.config_entries.async_update_entry(entry, title="Waterius")
        _LOGGER.info("Обновлён title интеграции с '%s' на 'Waterius'", entry.title)
    
    # Создаем менеджер устройств
    device_manager = DeviceManager(hass)
    
    # Загружаем устройства из конфигурации
    devices = entry.data.get(CONF_DEVICES, [])
    for device_config in devices:
        device_id = device_config.get(CONF_DEVICE_ID)
        device_name = device_config.get(CONF_DEVICE_NAME)
        device_mac = device_config.get(CONF_DEVICE_MAC)
        device_key = device_config.get(CONF_DEVICE_KEY)  # Серийный номер (key)
        if device_id and device_name:
            device_manager.add_device(device_id, device_name, device_mac)
            
            # Восстанавливаем серийный номер (key) из конфигурации
            if device_key:
                device = device_manager.get_device(device_id)
                if device and device.data:
                    device.data["key"] = device_key
                    _LOGGER.debug("Восстановлен серийный номер устройства %s: %s", device_id, device_key)
            
            _LOGGER.debug(
                "Загружено устройство: %s (%s)%s%s",
                device_name,
                device_id,
                f" с MAC {device_mac}" if device_mac else "",
                f" (key: {device_key})" if device_key else ""
            )
    
    # Создаем и запускаем веб-сервер с менеджером устройств
    # Использует стандартные эндпоинты Home Assistant: /api/waterius и /api/waterius/cfg
    # auto_add_devices читается динамически из entry.options
    web_server = WateriusWebServer(hass, device_manager, entry)
    try:
        await web_server.start()
    except Exception as e:
        _LOGGER.error("Не удалось запустить веб-сервер: %s", e)
        raise
    
    # Сохраняем веб-сервер и менеджер устройств в runtime_data
    entry.runtime_data = WateriusRuntimeData(
        web_server=web_server,
        device_manager=device_manager,
    )
    
    # Регистрируем сервис через Zeroconf для автоматического обнаружения устройствами
    try:
        from homeassistant.components import zeroconf
        from homeassistant.helpers.network import get_url
        from zeroconf import ServiceInfo
        import ipaddress
        import socket
        
        zeroconf_instance = await zeroconf.async_get_instance(hass)
        
        # Получаем hostname системы для Zeroconf
        hostname = socket.gethostname()
        
        # Получаем URL Home Assistant один раз для определения порта и IP адресов
        ha_url = None
        ha_port = 8123  # Порт по умолчанию
        try:
            # Пытаемся получить порт из HTTP компонента Home Assistant
            if hasattr(hass, "http") and hasattr(hass.http, "server_port") and hass.http.server_port:
                ha_port = hass.http.server_port
                _LOGGER.debug("Получен порт HTTP сервера из настроек HA: %s", ha_port)
                # Получаем URL для определения IP адресов
                ha_url = get_url(hass, prefer_external=False)
            else:
                # Fallback: получаем порт из URL
                ha_url = get_url(hass, prefer_external=False)
                if ha_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(ha_url)
                    # Определяем порт из URL
                    if parsed.port:
                        ha_port = parsed.port
                    elif parsed.scheme == "https":
                        ha_port = 443
                    elif parsed.scheme == "http":
                        ha_port = 80
                    _LOGGER.debug("Получен порт HTTP сервера из URL: %s", ha_port)
        except Exception as e:
            _LOGGER.debug("Не удалось получить порт из настроек HA, используем порт по умолчанию 8123: %s", e)
            # Пытаемся получить URL для определения IP адресов даже при ошибке
            try:
                ha_url = get_url(hass, prefer_external=False)
            except Exception:
                pass
        
        # Функция для проверки, является ли адрес пригодным для Zeroconf
        def is_valid_zeroconf_address(ip_str: str) -> bool:
            """Проверка, является ли IP адрес пригодным для регистрации в Zeroconf.
            
            Исключаются:
            - Loopback адреса (127.0.0.0/8)
            - Link-local адреса (169.254.0.0/16)
            - Docker/HassOS внутренние сети (172.30.0.0/16, 172.17.0.0/16)
            - Другие внутренние Docker сети (172.16.0.0/12, но не все)
            
            Args:
                ip_str: IP адрес в строковом формате
                
            Returns:
                True если адрес пригоден для Zeroconf, False иначе
            """
            try:
                ip_addr = ipaddress.IPv4Address(ip_str)
                
                # Исключаем loopback адреса (127.0.0.0/8)
                if ip_addr.is_loopback:
                    return False
                
                # Исключаем link-local адреса (169.254.0.0/16)
                if ip_addr.is_link_local:
                    return False
                
                # Исключаем Docker/HassOS внутренние сети
                # 172.30.0.0/16 - часто используется в HassOS/Docker
                # 172.17.0.0/16 - стандартная Docker сеть
                if ip_str.startswith("172.30.") or ip_str.startswith("172.17."):
                    return False
                
                # Оставляем только приватные адреса, которые доступны из локальной сети
                # 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12 (кроме исключенных выше)
                return ip_addr.is_private
            except (ValueError, ipaddress.AddressValueError):
                return False
        
        # Сохраняем hostname из настроек Home Assistant для отображения в sensor
        ha_hostname_from_url = None
        
        # Получаем все локальные IPv4 адреса Home Assistant (только IPv4, так как устройства не поддерживают IPv6)
        local_addresses = []
        
        # Метод 1: Получаем IP из настроек Home Assistant (используем уже полученный ha_url)
        if ha_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(ha_url)
                if parsed.hostname:
                    # Сохраняем hostname, если это не IP адрес
                    try:
                        ipaddress.IPv4Address(parsed.hostname)
                        # Это IP адрес, не hostname
                    except (ValueError, ipaddress.AddressValueError):
                        # Это hostname, сохраняем его
                        ha_hostname_from_url = parsed.hostname
                    
                    # Проверяем, является ли hostname IPv4 адресом
                    try:
                        ip_addr = ipaddress.IPv4Address(parsed.hostname)
                        if is_valid_zeroconf_address(str(ip_addr)):
                            local_addresses.append(str(ip_addr))
                    except (ValueError, ipaddress.AddressValueError):
                        # Это hostname, нужно получить IPv4 адрес
                        try:
                            resolved_ip = socket.gethostbyname(parsed.hostname)
                            if is_valid_zeroconf_address(resolved_ip):
                                local_addresses.append(resolved_ip)
                        except (socket.gaierror, OSError, ValueError, ipaddress.AddressValueError):
                            pass
            except Exception as e:
                _LOGGER.debug("Не удалось получить IP из URL: %s", e)
        
        # Метод 2: Получаем все локальные IPv4 адреса из сетевых интерфейсов
        try:
            import netifaces
            for interface in netifaces.interfaces():
                try:
                    addrs = netifaces.ifaddresses(interface)
                    # Только IPv4 адреса (IPv6 не поддерживается устройствами)
                    if netifaces.AF_INET in addrs:
                        for addr_info in addrs[netifaces.AF_INET]:
                            ip = addr_info.get("addr")
                            if ip and is_valid_zeroconf_address(ip) and ip not in local_addresses:
                                local_addresses.append(ip)
                except (OSError, ValueError):
                    continue
        except ImportError:
            # netifaces не установлен, используем только метод 1 (из настроек HA)
            _LOGGER.debug("netifaces не установлен, используем только IP из настроек Home Assistant")
        except Exception as e:
            _LOGGER.debug("Не удалось получить IP из сетевых интерфейсов: %s", e)
        
        # Логируем отфильтрованные адреса для отладки
        if local_addresses:
            _LOGGER.debug(
                "Отфильтрованы пригодные для Zeroconf IPv4 адреса: %s",
                ", ".join(local_addresses),
            )
        else:
            _LOGGER.warning(
                "Не удалось определить пригодные IPv4 адреса Home Assistant для Zeroconf "
                "(исключены loopback, link-local и Docker/HassOS внутренние сети), "
                "пропускаем Zeroconf регистрацию"
            )
            raise ZeroconfAddressError()
        
        # Преобразуем IPv4 адреса в бинарный формат для Zeroconf
        binary_addresses = []
        for ip_str in local_addresses:
            try:
                ip_addr = ipaddress.IPv4Address(ip_str)
                binary_addresses.append(socket.inet_aton(ip_str))
            except (ValueError, ipaddress.AddressValueError):
                _LOGGER.debug("Пропускаем невалидный IPv4 адрес: %s", ip_str)
        
        if not binary_addresses:
            _LOGGER.warning(
                "Не удалось преобразовать IPv4 адреса в бинарный формат, пропускаем Zeroconf регистрацию"
            )
            raise ZeroconfConversionError()
        
        # Объявляем сервис через Zeroconf используя ServiceInfo из zeroconf библиотеки
        # Регистрируем все локальные IPv4 адреса для поддержки устройств в разных подсетях
        # Используем порт HTTP сервера Home Assistant, а не порт интеграции
        service_info = ServiceInfo(
            type_="_waterius._tcp.local.",
            name=f"Waterius Home Assistant {entry.entry_id[:8]}._waterius._tcp.local.",
            addresses=binary_addresses,  # Все локальные IPv4 адреса
            port=ha_port,  # Порт HTTP сервера Home Assistant
            weight=0,
            priority=0,
            properties={
                b"version": b"1.0.0",
                b"domain": DOMAIN.encode(),
                b"entry_id": entry.entry_id.encode(),
            },
            server=f"{hostname}.local.",  # Server hostname для резолвинга
        )
        
        # Пытаемся зарегистрировать сервис
        try:
            await zeroconf_instance.async_register_service(service_info)
        except Exception as register_error:
            # Если сервис уже зарегистрирован, пытаемся его отменить и зарегистрировать заново
            from zeroconf._exceptions import NonUniqueNameException
            if isinstance(register_error, NonUniqueNameException):
                _LOGGER.warning(
                    "Zeroconf сервис %s уже зарегистрирован, пытаемся отменить регистрацию и зарегистрировать заново",
                    service_info.name
                )
                try:
                    # Отменяем регистрацию старого сервиса
                    await zeroconf_instance.async_unregister_service(service_info)
                    # Задержка для завершения отмены регистрации (увеличена до 1 сек)
                    import asyncio
                    await asyncio.sleep(1.0)
                    # Регистрируем заново
                    await zeroconf_instance.async_register_service(service_info)
                    _LOGGER.info("Успешно переregister Zeroconf сервиса после удаления старой регистрации")
                except Exception as retry_error:
                    _LOGGER.warning("Не удалось переregister Zeroconf сервиса: %s. Продолжаем без Zeroconf.", retry_error)
                    # НЕ поднимаем исключение - интеграция должна работать без Zeroconf
            else:
                _LOGGER.warning("Ошибка регистрации Zeroconf сервиса: %s. Продолжаем без Zeroconf.", register_error)
        
        _LOGGER.info(
            "Зарегистрирован Zeroconf сервис для автоматического обнаружения: "
            "%s на адресах %s:%s (порт HTTP сервера Home Assistant)",
            service_info.name,
            ", ".join(local_addresses),
            ha_port,
        )
        
        # Сохраняем информацию для повторной попытки при необходимости
        entry.runtime_data.zeroconf_service_info = service_info
        entry.runtime_data.zeroconf_registered = True
        entry.runtime_data.ha_hostname = ha_hostname_from_url if 'ha_hostname_from_url' in locals() else None
        # local_addresses не нужно сохранять - данные берутся из service_info
        
        # Уведомляем sensor о изменении статуса
        hass.bus.async_fire(
            "waterius_zeroconf_status_changed",
            {
                "entry_id": entry.entry_id,
                "registered": True,
            },
        )
    except Exception as e:
        _LOGGER.warning(
            "Не удалось зарегистрировать Zeroconf сервис для автоматического обнаружения: %s",
            e,
            exc_info=True,
        )
        # Сохраняем информацию для повторной попытки
        entry.runtime_data.zeroconf_service_info = service_info if 'service_info' in locals() else None
        entry.runtime_data.zeroconf_registered = False
        
        # Уведомляем sensor о изменении статуса
        hass.bus.async_fire(
            "waterius_zeroconf_status_changed",
            {
                "entry_id": entry.entry_id,
                "registered": False,
            },
        )
        
        # Планируем повторную попытку через 30 секунд
        async def retry_zeroconf_registration() -> None:
            """Повторная попытка регистрации Zeroconf сервиса."""
            import asyncio
            await asyncio.sleep(30)  # Ждем 30 секунд
            try:
                # Получаем zeroconf instance заново
                from homeassistant.components import zeroconf as zeroconf_module
                zeroconf_retry = await zeroconf_module.async_get_instance(hass)
                
                if entry.runtime_data and not entry.runtime_data.zeroconf_registered:
                    service_info_retry = entry.runtime_data.zeroconf_service_info
                    if service_info_retry:
                        await zeroconf_retry.async_register_service(service_info_retry)
                        entry.runtime_data.zeroconf_registered = True
                        _LOGGER.info(
                            "Успешно зарегистрирован Zeroconf сервис после повторной попытки"
                        )
                        # Уведомляем sensor о изменении статуса
                        hass.bus.async_fire(
                            "waterius_zeroconf_status_changed",
                            {
                                "entry_id": entry.entry_id,
                                "registered": True,
                            },
                        )
            except Exception as retry_error:
                _LOGGER.debug(
                    "Повторная попытка регистрации Zeroconf не удалась: %s", retry_error
                )
        
        hass.async_create_task(retry_zeroconf_registration())
    
    # Регистрируем платформы
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Проверяем здоровье интеграции и создаем repair issues при необходимости
    from .health import async_check_integration_health
    await async_check_integration_health(
        hass,
        entry.entry_id,
        device_manager,
    )
    
    _LOGGER.info(
        "Интеграция Waterius инициализирована с %d устройствами",
        len(devices)
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WateriusConfigEntry) -> bool:
    """Выгрузка интеграции."""
    # Останавливаем веб-сервер
    if entry.runtime_data:
        await entry.runtime_data.web_server.stop()
        
        # Отменяем регистрацию Zeroconf сервиса
        if entry.runtime_data.zeroconf_registered and entry.runtime_data.zeroconf_service_info:
            try:
                from homeassistant.components import zeroconf
                import asyncio
                zeroconf_instance = await zeroconf.async_get_instance(hass)
                await zeroconf_instance.async_unregister_service(entry.runtime_data.zeroconf_service_info)
                # Небольшая задержка для завершения отмены регистрации
                await asyncio.sleep(0.5)
                _LOGGER.info("Отменена регистрация Zeroconf сервиса")
            except Exception as e:
                _LOGGER.debug("Не удалось отменить регистрацию Zeroconf сервиса: %s", e)
        
        # runtime_data автоматически очистится при выгрузке entry
    
    # Выгружаем платформы
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        _LOGGER.info("Интеграция Waterius выгружена")
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: WateriusConfigEntry) -> None:
    """Перезагрузка интеграции."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: WateriusConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Удаление устройства из интеграции.
    
    Эта функция вызывается, когда пользователь удаляет устройство через UI.
    
    Args:
        hass: Экземпляр Home Assistant
        entry: Config entry интеграции
        device_entry: Запись устройства из device registry
        
    Returns:
        True если устройство можно удалить, False если нельзя
    """
    # Получаем device_id из identifiers устройства
    device_id = None
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            # Identifier может быть device_id или MAC адресом
            # device_id имеет формат "waterius_XXXX"
            if identifier[1].startswith("waterius_"):
                device_id = identifier[1]
                break
            # Если это MAC адрес, ищем устройство по MAC
            elif ":" in identifier[1]:
                mac = identifier[1]
                if entry.runtime_data:
                    device = entry.runtime_data.device_manager.get_device_by_mac(mac)
                    if device:
                        device_id = device.device_id
                        break
    
    if not device_id:
        _LOGGER.warning(
            "Не удалось найти device_id для устройства %s",
            device_entry.name
        )
        return False
    
    # Удаляем устройство из device_manager
    if entry.runtime_data:
        success = entry.runtime_data.device_manager.remove_device(device_id)
        if not success:
            _LOGGER.warning(
                "Не удалось удалить устройство %s из device_manager",
                device_id
            )
            return False
    
    # Обновляем config entry: удаляем устройство из списка
    devices = entry.data.get(CONF_DEVICES, [])
    updated_devices = [
        device for device in devices
        if device.get(CONF_DEVICE_ID) != device_id
    ]
    
    # Сохраняем обновленную конфигурацию
    new_data = {**entry.data, CONF_DEVICES: updated_devices}
    hass.config_entries.async_update_entry(entry, data=new_data)
    
    _LOGGER.info(
        "Устройство %s (%s) успешно удалено из интеграции",
        device_entry.name,
        device_id
    )
    
    return True


def update_device_key_in_config(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    device_key: str,
) -> None:
    """Обновление серийного номера (key) устройства в конфигурации.
    
    Вызывается когда от устройства приходит новый key или key изменился.
    
    Args:
        hass: Экземпляр Home Assistant
        entry: Config entry интеграции
        device_id: ID устройства
        device_key: Серийный номер устройства (key)
    """
    devices = entry.data.get(CONF_DEVICES, [])
    updated = False
    
    # Ищем устройство и обновляем его key
    for device in devices:
        if device.get(CONF_DEVICE_ID) == device_id:
            # Проверяем, изменился ли key
            current_key = device.get(CONF_DEVICE_KEY)
            if current_key != device_key:
                device[CONF_DEVICE_KEY] = device_key
                updated = True
                _LOGGER.debug(
                    "Обновлен серийный номер устройства %s: %s -> %s",
                    device_id,
                    current_key or "(не установлен)",
                    device_key
                )
            break
    
    # Если были изменения, сохраняем конфигурацию
    if updated:
        new_data = {**entry.data, CONF_DEVICES: devices}
        hass.config_entries.async_update_entry(entry, data=new_data)
        _LOGGER.debug("Конфигурация обновлена с новым серийным номером для %s", device_id)

