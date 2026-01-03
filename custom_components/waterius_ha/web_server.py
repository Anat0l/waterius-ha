"""Веб-сервер для приема данных через POST запросы с JSON."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MAC,
    CONF_DEVICE_KEY,
    MAX_JSON_SIZE,
)
from .exceptions import (
    InvalidEncodingError,
    InvalidJSONError,
    InvalidMACAddressError,
    InvalidRequestError,
)
from .validators import validate_device_data, sanitize_device_data

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)


class WateriusDataView(HomeAssistantView):
    """View для обработки POST запросов от устройств Waterius."""

    url = "/api/waterius"
    name = "api:waterius"
    requires_auth = False

    def __init__(
        self,
        hass: HomeAssistant,
        device_manager: DeviceManager | None,
        config_entry: ConfigEntry | None,
        web_server: "WateriusWebServer | None" = None,
    ) -> None:
        """Инициализация view."""
        self.hass = hass
        self.device_manager = device_manager
        self.config_entry = config_entry
        self.web_server = web_server
    
    @property
    def auto_add_devices(self) -> bool:
        """Получить текущее значение настройки автодобавления из web_server."""
        if self.web_server:
            return self.web_server.auto_add_devices
        # Fallback если web_server не задан
        return True

    async def post(self, request: web.Request) -> web.Response:
        """Обработка POST запросов с JSON данными.
        
        Args:
            request: HTTP запрос от устройства
            
        Returns:
            JSON ответ с результатом обработки
        """
        try:
            # Проверяем размер тела запроса перед парсингом
            content_length = request.headers.get("Content-Length")
            if content_length:
                try:
                    size = int(content_length)
                    if size > MAX_JSON_SIZE:
                        _LOGGER.warning(
                            "Размер запроса превышает максимальный: %d байт (максимум %d)",
                            size,
                            MAX_JSON_SIZE,
                        )
                        return self.json_message(
                            f"Request too large: {size} bytes (max {MAX_JSON_SIZE})",
                            status_code=413,
                        )
                except ValueError:
                    pass  # Если не удалось распарсить, продолжаем
            
            # Получаем JSON данные из тела запроса с ограничением размера
            try:
                # Читаем тело запроса с ограничением размера
                body = await request.read()
                if len(body) > MAX_JSON_SIZE:
                    _LOGGER.warning(
                        "Размер тела запроса превышает максимальный: %d байт (максимум %d)",
                        len(body),
                        MAX_JSON_SIZE,
                    )
                    return self.json_message(
                        f"Request body too large: {len(body)} bytes (max {MAX_JSON_SIZE})",
                        status_code=413,
                    )
                
                # Парсим JSON из прочитанного тела
                json_data: dict[str, Any] = json.loads(body.decode("utf-8"))
            except UnicodeDecodeError as e:
                _LOGGER.error("Ошибка при декодировании тела запроса: %s", e)
                error = InvalidEncodingError()
                return self.json_message(error.translation_key, status_code=400)
            except json.JSONDecodeError as e:
                _LOGGER.error("Ошибка при парсинге JSON: %s", e)
                error = InvalidJSONError()
                return self.json_message(error.translation_key, status_code=400)
            except Exception as e:
                _LOGGER.error("Ошибка при обработке запроса: %s", e)
                error = InvalidRequestError()
                return self.json_message(error.translation_key, status_code=400)

            # Валидация и очистка данных от устройства
            is_valid, validation_errors = validate_device_data(json_data)
            if not is_valid:
                _LOGGER.warning(
                    "Данные от устройства не прошли валидацию: %s",
                    "; ".join(validation_errors),
                )
                # Не блокируем запрос, но логируем предупреждение
                # Очищаем данные для безопасности
                json_data = sanitize_device_data(json_data)
            else:
                # Очищаем данные даже если валидация прошла
                json_data = sanitize_device_data(json_data)

            # Получаем путь запроса
            path = request.path

            # Извлекаем и валидируем MAC адрес из JSON для идентификации устройства
            mac_address = json_data.get("mac")
            device = None
            device_id = None

            # Валидация формата MAC адреса
            if mac_address:
                mac_address = self._validate_and_normalize_mac(mac_address)
                if not mac_address:
                    _LOGGER.warning("Неверный формат MAC адреса: %s", json_data.get("mac"))
                    error = InvalidMACAddressError(str(json_data.get("mac")))
                    return self.json_message(error.translation_key, status_code=400)

            if mac_address and self.device_manager:
                # Ищем устройство по MAC адресу
                device = self.device_manager.get_device_by_mac(mac_address)
                if device:
                    device_id = device.device_id
                    _LOGGER.debug(
                        "Найдено устройство %s (%s) по MAC %s",
                        device.name,
                        device_id,
                        mac_address,
                    )
                else:
                    # Устройство не найдено - проверяем, нужно ли добавить автоматически
                    if self.auto_add_devices:
                        _LOGGER.debug(
                            "Устройство с MAC %s не найдено, пытаемся добавить автоматически...",
                            mac_address,
                        )
                        device_id, device_name = await self._auto_add_device(
                            mac_address, json_data
                        )
                        if device_id:
                            device = self.device_manager.get_device(device_id)
                            if device:
                                _LOGGER.info(
                                    "✓ Автоматически добавлено устройство: %s (%s) с MAC %s",
                                    device_name,
                                    device_id,
                                    mac_address,
                                )
                            else:
                                _LOGGER.error(
                                    "Устройство %s было добавлено, но не найдено в менеджере",
                                    device_id,
                                )
                        else:
                            _LOGGER.warning(
                                "Не удалось автоматически добавить устройство с MAC %s",
                                mac_address,
                            )
                    else:
                        _LOGGER.warning(
                            "Устройство с MAC %s не найдено в конфигурации (автоматическое добавление выключено)",
                            mac_address,
                        )

            # Логируем на уровне DEBUG для уменьшения шума в логах
            _LOGGER.debug(
                "Получен POST запрос на %s от устройства %s (MAC: %s)",
                path,
                device_id or "неизвестное",
                mac_address or "не указан",
            )

            # Если устройство найдено (или было добавлено), обновляем его данные
            if device and device_id:
                self.device_manager.update_device_data(device_id, json_data)
                
                # Если в данных есть серийный номер (key), сохраняем его в конфигурацию
                if "key" in json_data and self.config_entry:
                    from . import update_device_key_in_config
                    device_key = json_data["key"]
                    # Вызываем синхронную функцию обновления конфигурации
                    # (она сама вызовет async_update_entry через callback)
                    update_device_key_in_config(self.hass, self.config_entry, device_id, str(device_key))

                # Логируем данные в системный лог HA
                self._log_device_data(device.name, device_id, json_data, request)

                # Отправляем событие для конкретного устройства
                self.hass.bus.async_fire(
                    "waterius_device_data_received",
                    {
                        "device_id": device_id,
                        "device_name": device.name,
                        "mac": mac_address,
                        "data": json_data,
                        "remote": str(request.remote) if request.remote else None,
                    },
                )
            else:
                # Логируем данные неизвестного устройства в системный лог HA
                self._log_unknown_device_data(json_data, mac_address, request)

                # Отправляем общее событие, если устройство не найдено
                self.hass.bus.async_fire(
                    "waterius_data_received",
                    {
                        "path": path,
                        "data": json_data,
                        "mac": mac_address,
                        "device_id": device_id,
                        "remote": str(request.remote) if request.remote else None,
                    },
                )

            # Возвращаем успешный ответ
            return self.json(
                {
                    "status": "ok",
                    "message": "Данные получены",
                    "path": path,
                    "device_id": device_id,
                    "device_name": device.name if device else None,
                    "mac": mac_address,
                }
            )
        except Exception as e:
            _LOGGER.error("Ошибка при обработке POST запроса: %s", e, exc_info=True)
            return self.json_message(str(e), status_code=500)

    async def get(self, request: web.Request) -> web.Response:
        """Обработка GET запросов (для обратной совместимости)."""
        try:
            # Получаем параметры из URL
            query_params = dict(request.query)
            path = request.path

            _LOGGER.debug(
                "Получен GET запрос на %s с параметрами: %s", path, query_params
            )

            # Отправляем событие в Home Assistant
            self.hass.bus.async_fire(
                "waterius_data_received",
                {
                    "path": path,
                    "query_params": query_params,
                    "remote": str(request.remote) if request.remote else None,
                },
            )

            return self.json(
                {
                    "status": "ok",
                    "message": "GET запрос получен (используйте POST для отправки JSON)",
                    "path": path,
                }
            )
        except Exception as e:
            _LOGGER.error("Ошибка при обработке GET запроса: %s", e)
            return self.json_message(str(e), status_code=500)

    def _validate_and_normalize_mac(self, mac_address: str) -> str | None:
        """Валидация и нормализация MAC адреса.
        
        Args:
            mac_address: MAC адрес для валидации
            
        Returns:
            Нормализованный MAC адрес в формате XX:XX:XX:XX:XX:XX или None если невалидный
        """
        if not isinstance(mac_address, str):
            return None
        
        # Удаляем все символы, кроме шестнадцатеричных цифр
        normalized = "".join(filter(lambda x: x in "0123456789abcdefABCDEF", mac_address))
        
        # Проверяем длину (должно быть 12 символов)
        if len(normalized) != 12:
            return None
        
        # Форматируем в стандартный вид XX:XX:XX:XX:XX:XX
        return ":".join(normalized[i:i+2] for i in range(0, 12, 2)).upper()

    async def _generate_device_notification_svg(
        self, device_name: str, mac_address: str
    ) -> str:
        """Генерация SVG с WebP фоном (встроенным в base64) и текстом поверх.
        
        Args:
            device_name: Название устройства (например, "Waterius #705E")
            mac_address: MAC адрес устройства
            
        Returns:
            SVG изображение как строка
        """
        import base64
        import os
        
        # Путь к WebP файлу
        www_path = os.path.join(os.path.dirname(__file__), "www")
        webp_path = os.path.join(www_path, "waterius-device.webp")
        
        # Читаем WebP и конвертируем в base64 data URI
        webp_data_uri = ""
        if os.path.exists(webp_path):
            try:
                # Используем asyncio.to_thread для неблокирующего чтения файла
                def read_webp() -> bytes:
                    with open(webp_path, "rb") as f:
                        return f.read()
                
                webp_bytes = await asyncio.to_thread(read_webp)
                webp_base64 = base64.b64encode(webp_bytes).decode('utf-8')
                webp_data_uri = f"data:image/webp;base64,{webp_base64}"
                _LOGGER.debug("WebP изображение загружено и конвертировано в base64 (%d байт)", len(webp_bytes))
            except Exception as e:
                _LOGGER.debug("Не удалось загрузить WebP изображение: %s", e)
        else:
            _LOGGER.debug("WebP файл не найден: %s", webp_path)
        
        # Если WebP не загружен, используем цветной градиент вместо фона
        background = ""
        if webp_data_uri:
            background = f'<image href="{webp_data_uri}" x="0" y="0" width="400" height="400" preserveAspectRatio="xMidYMid meet"/>'
        else:
            # Fallback: красивый градиентный фон
            background = '''
  <defs>
    <linearGradient id="bgGradient" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#2c3e50;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#3498db;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="400" height="400" fill="url(#bgGradient)"/>
  <circle cx="200" cy="200" r="80" fill="#ecf0f1" opacity="0.1"/>
  <text x="200" y="220" font-family="Arial, sans-serif" font-size="60" font-weight="bold" 
        fill="#ecf0f1" text-anchor="middle" opacity="0.5">💧</text>'''
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 400 500" width="400" height="500">
  <!-- Фон (WebP или градиент) -->
  {background}
  
  <!-- Текст: Название устройства -->
  <text x="205" y="230" font-family="Arial, sans-serif" font-size="28" font-weight="bold" 
        fill="#000000" text-anchor="middle">{device_name}</text>
  
  <!-- Текст: MAC адрес -->
  <text x="205" y="270" font-family="Courier New, monospace" font-size="16" 
        fill="#000000" text-anchor="middle" textLength="180" lengthAdjust="spacingAndGlyphs">MAC: {mac_address}</text>
</svg>'''
        return svg

    async def _schedule_device_notification(
        self, device_id: str, device_name: str, mac_address: str
    ) -> None:
        """Запланировать создание notification через callback после создания device entry.
        
        Подписывается на события device registry и создает notification когда
        device entry будет создан.
        
        Args:
            device_id: ID устройства
            device_name: Название устройства
            mac_address: MAC адрес устройства
        """
        from homeassistant.components import persistent_notification
        from homeassistant.helpers import device_registry as dr
        from homeassistant.core import callback
        import base64
        
        # Генерируем SVG заранее
        svg_content = await self._generate_device_notification_svg(device_name, mac_address)
        svg_base64 = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
        image_url = f"data:image/svg+xml;base64,{svg_base64}"
        
        device_registry = dr.async_get(self.hass)
        identifiers = {(DOMAIN, device_id)}
        if mac_address:
            identifiers.add((DOMAIN, mac_address))
        
        # Проверяем, может device entry уже создан
        device_entry = device_registry.async_get_device(identifiers=identifiers)
        if device_entry:
            # Device entry уже есть, создаем notification сразу
            self._create_device_notification(
                device_id, device_name, image_url, device_entry
            )
            _LOGGER.debug("✓ Device entry уже существует, notification создан сразу")
            return
        
        # Device entry еще не создан, подписываемся на событие
        notification_created = False
        
        @callback
        def device_registry_updated(event: Any) -> None:
            """Callback на обновление device registry."""
            nonlocal device_entry, notification_created
            
            if notification_created:
                return
            
            # Проверяем, наше ли это устройство
            if event.data.get("action") != "create":
                return
            
            # Проверяем device_id из события
            event_device_id = event.data.get("device_id")
            if not event_device_id:
                return
            
            # Получаем device entry
            registry_device = device_registry.async_get(event_device_id)
            if not registry_device:
                return
            
            # Проверяем идентификаторы
            if not identifiers.intersection(registry_device.identifiers):
                return
            
            # Это наше устройство!
            device_entry = registry_device
            notification_created = True
            _LOGGER.debug("✓ Device entry создан для %s через callback", device_id)
            
            # Создаем notification
            self._create_device_notification(
                device_id, device_name, image_url, device_entry
            )
            
            # Отписываемся от события
            remove_listener()
            if cancel_timeout:
                cancel_timeout()
        
        @callback
        def timeout_callback() -> None:
            """Callback на таймаут - создаем notification без ссылки."""
            nonlocal notification_created
            
            if notification_created:
                return
                
            notification_created = True
            _LOGGER.info(
                "Таймаут ожидания device entry для %s. "
                "Создаем notification без ссылки.",
                device_id
            )
            
            # Создаем notification без device entry (без ссылки)
            self._create_device_notification(
                device_id, device_name, image_url, None
            )
            
            # Отписываемся от события
            remove_listener()
        
        # Подписываемся на событие device registry
        remove_listener = self.hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            device_registry_updated
        )
        
        # Устанавливаем таймаут на 10 секунд
        from homeassistant.helpers.event import async_call_later
        cancel_timeout = async_call_later(self.hass, 10, timeout_callback)
        
        _LOGGER.debug("📡 Подписка на EVENT_DEVICE_REGISTRY_UPDATED для %s (таймаут: 10 сек)", device_id)
    
    def _create_device_notification(
        self,
        device_id: str,
        device_name: str,
        image_url: str,
        device_entry: Any,
    ) -> None:
        """Создать notification о новом устройстве.
        
        Args:
            device_id: ID устройства
            device_name: Название устройства
            image_url: URL изображения (data URI)
            device_entry: Device entry из registry
        """
        from homeassistant.components import persistent_notification
        
        # Формируем сообщение с изображением
        message_parts = [
            f"![Waterius Device]({image_url})",
            "",  # Пустая строка для отступа
        ]
        
        # Добавляем ссылку на устройство
        if device_entry:
            device_url = f"/config/devices/device/{device_entry.id}"
            message_parts.append("")
            message_parts.append(f"[🔧 Перейти к настройкам устройства]({device_url})")
            _LOGGER.debug("✓ Добавлена ссылка на устройство: %s", device_url)
        
        message = "\n".join(message_parts)
        
        persistent_notification.async_create(
            self.hass,
            message,
            title="🎉 Waterius: Новое устройство",
            notification_id=f"waterius_device_added_{device_id}",
        )
        _LOGGER.debug("✓ Notification создан для устройства %s", device_name)

    def _log_device_data(
        self,
        device_name: str,
        device_id: str,
        data: dict[str, Any],
        request: web.Request,
    ) -> None:
        """Логирование данных устройства в системный лог Home Assistant.
        
        Args:
            device_name: Имя устройства
            device_id: ID устройства
            data: Данные от устройства
            request: HTTP запрос
        """
        try:
            # Логируем в системный лог (стандартный подход HA)
            _LOGGER.debug(
                "📥 Данные от %s (%s): CH0=%s, CH1=%s, voltage=%sV, battery=%s%%, rssi=%s",
                device_name,
                device_id,
                data.get("ch0", "N/A"),
                data.get("ch1", "N/A"),
                data.get("voltage", "N/A"),
                data.get("battery", "N/A"),
                data.get("rssi", "N/A")
            )
        except Exception as e:
            _LOGGER.error("Ошибка при логировании данных устройства: %s", e)

    def _log_unknown_device_data(
        self, data: dict[str, Any], mac: str | None, request: web.Request
    ) -> None:
        """Логирование данных неизвестного устройства в системный лог Home Assistant.
        
        Args:
            data: Данные от устройства
            mac: MAC адрес устройства (если известен)
            request: HTTP запрос
        """
        try:
            # Логируем в системный лог (стандартный подход HA)
            _LOGGER.info(
                "📥 Получены данные от неизвестного устройства: MAC=%s, CH0=%s, CH1=%s, key=%s",
                mac or "не указан",
                data.get("ch0", "N/A"),
                data.get("ch1", "N/A"),
                data.get("key", "N/A")
            )
        except Exception as e:
            _LOGGER.error(
                "Ошибка при логировании данных неизвестного устройства: %s", e
            )

    async def _auto_add_device(
        self, mac_address: str, json_data: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        """Автоматическое добавление устройства.
        
        Args:
            mac_address: MAC адрес устройства (уже валидированный)
            json_data: JSON данные от устройства
            
        Returns:
            Кортеж (device_id, device_name) или (None, None) при ошибке
        """
        if not self.device_manager or not self.config_entry:
            return None, None

        try:
            # Валидируем MAC адрес еще раз для безопасности
            normalized_mac = self._validate_and_normalize_mac(mac_address)
            if not normalized_mac:
                _LOGGER.error("Неверный формат MAC адреса при автоматическом добавлении: %s", mac_address)
                return None, None
            
            # Генерируем device_id на основе нормализованного MAC адреса
            device_id = f"waterius_{normalized_mac.replace(':', '_').lower()}"

            # Генерируем имя устройства на основе MAC адреса
            # Используем последние 4 символа MAC адреса с символом # перед ними
            mac_short = normalized_mac.replace(":", "")[-4:].upper()
            device_name = f"Waterius #{mac_short}"

            # Проверяем, не существует ли уже устройство с таким ID или MAC
            existing_device = self.device_manager.get_device(device_id)
            if existing_device:
                _LOGGER.warning("Устройство с ID %s уже существует", device_id)
                return None, None

            # Проверяем по MAC адресу (используем нормализованный)
            existing_by_mac = self.device_manager.get_device_by_mac(normalized_mac)
            if existing_by_mac:
                _LOGGER.warning(
                    "Устройство с MAC %s уже существует как %s",
                    normalized_mac,
                    existing_by_mac.device_id,
                )
                return None, None

            # Проверяем, нет ли уже устройства с таким MAC в config entry (дополнительная проверка)
            current_devices = self.config_entry.data.get(CONF_DEVICES, [])
            if any(
                self._validate_and_normalize_mac(d.get(CONF_DEVICE_MAC, "")) == normalized_mac
                for d in current_devices
            ):
                _LOGGER.warning(
                    "Устройство с MAC %s уже есть в конфигурации", normalized_mac
                )
                return None, None

            # Добавляем устройство в менеджер с нормализованным MAC
            if not self.device_manager.add_device(
                device_id, device_name, normalized_mac
            ):
                _LOGGER.error(
                    "Не удалось добавить устройство %s в менеджер", device_id
                )
                return None, None

            # Убеждаемся, что устройство добавлено в менеджер
            added_device = self.device_manager.get_device(device_id)
            if not added_device:
                _LOGGER.error(
                    "Устройство %s не найдено в менеджере после добавления", device_id
                )
                return None, None

            # Сохраняем устройство в config entry с нормализованным MAC
            new_device = {
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: device_name,
                CONF_DEVICE_MAC: normalized_mac,
            }
            
            # Добавляем серийный номер (key), если он есть в данных от устройства
            if "key" in json_data:
                new_device[CONF_DEVICE_KEY] = str(json_data["key"])
                _LOGGER.debug("Сохранен серийный номер устройства %s: %s", device_id, json_data["key"])
            
            updated_devices = current_devices + [new_device]
            new_data = {**self.config_entry.data, CONF_DEVICES: updated_devices}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            _LOGGER.info(
                "✓ Устройство %s (%s) успешно добавлено и сохранено в конфигурацию",
                device_name,
                device_id,
            )

            # ⚠️ ВАЖНО: Обновляем данные устройства ПЕРЕД отправкой события!
            # Это позволяет select'ам инициализироваться с правильными значениями от устройства
            # вместо fallback на "NOT_USED"
            if not self.device_manager.update_device_data(device_id, json_data):
                _LOGGER.error("Не удалось обновить данные устройства %s", device_id)
            else:
                _LOGGER.debug("Данные устройства %s обновлены из POST запроса перед созданием entities", device_id)
            
            # Отправляем событие для создания entities
            self.hass.bus.async_fire(
                "waterius_device_added",
                {
                    "device_id": device_id,
                    "device_name": device_name,
                    "device_mac": normalized_mac,
                    "entry_id": self.config_entry.entry_id,
                },
            )
            _LOGGER.debug("Событие waterius_device_added отправлено для %s", device_id)

            # Подписываемся на создание device entry через callback
            # вместо использования задержек и циклов
            await self._schedule_device_notification(device_id, device_name, normalized_mac)

            return device_id, device_name
        except Exception as e:
            _LOGGER.error("Ошибка при автоматическом добавлении устройства: %s", e)
            return None, None


class WateriusConfigView(HomeAssistantView):
    """View для получения настроек устройствами Waterius."""

    url = "/api/waterius/cfg"
    name = "api:waterius:config"
    requires_auth = False

    def __init__(
        self,
        hass: HomeAssistant,
        device_manager: DeviceManager | None,
        web_server: "WateriusWebServer | None" = None,
    ) -> None:
        """Инициализация view."""
        self.hass = hass
        self.device_manager = device_manager
        self.web_server = web_server

    async def post(self, request: web.Request) -> web.Response:
        """Обработка POST запросов для получения настроек устройства.
        
        Устройство отправляет свой MAC адрес, и получает в ответ настройки.
        
        Args:
            request: HTTP запрос от устройства
            
        Returns:
            JSON ответ с настройками устройства или сообщение об ошибке
        """
        try:
            # Получаем JSON данные из тела запроса
            try:
                body = await request.read()
                if len(body) > MAX_JSON_SIZE:
                    _LOGGER.warning(
                        "Размер запроса настроек превышает максимальный: %d байт (максимум %d)",
                        len(body),
                        MAX_JSON_SIZE,
                    )
                    return self.json_message(
                        f"Request too large: {len(body)} bytes (max {MAX_JSON_SIZE})",
                        status_code=413,
                    )
                
                json_data: dict[str, Any] = json.loads(body.decode("utf-8"))
            except UnicodeDecodeError as e:
                _LOGGER.error("Ошибка при декодировании запроса настроек: %s", e)
                error = InvalidEncodingError()
                return self.json_message(error.translation_key, status_code=400)
            except json.JSONDecodeError as e:
                _LOGGER.error("Ошибка при парсинге JSON запроса настроек: %s", e)
                error = InvalidJSONError()
                return self.json_message(error.translation_key, status_code=400)
            except Exception as e:
                _LOGGER.error("Ошибка при обработке запроса настроек: %s", e)
                error = InvalidRequestError()
                return self.json_message(error.translation_key, status_code=400)

            # Извлекаем идентификатор устройства из JSON (MAC или key)
            mac_address = json_data.get("mac")
            key = json_data.get("key")
            
            if not mac_address and not key:
                _LOGGER.warning("Запрос настроек без MAC адреса или key")
                return self.json_message("MAC address or key required", status_code=400)

            # Проверяем DeviceManager
            if not self.device_manager:
                _LOGGER.error("DeviceManager не инициализирован")
                return self.json_message("Service not available", status_code=503)

            # Ищем устройство по key (приоритет) или по MAC адресу
            device = None
            identifier = None
            identifier_type = None
            
            if key:
                # Поиск по key (серийному номеру)
                device = self.device_manager.get_device_by_serial(key)
                identifier = key
                identifier_type = "key"
                
                if not device:
                    _LOGGER.debug(
                        "Запрос настроек от неизвестного устройства с key: %s",
                        key
                    )
                    # Если есть MAC, попробуем найти по нему
                    if mac_address:
                        _LOGGER.debug("Попытка поиска по MAC адресу")
                        normalized_mac = self._validate_and_normalize_mac(mac_address)
                        if normalized_mac:
                            device = self.device_manager.get_device_by_mac(normalized_mac)
                            if device:
                                identifier = normalized_mac
                                identifier_type = "mac"
            
            if not device and mac_address:
                # Поиск по MAC адресу
                normalized_mac = self._validate_and_normalize_mac(mac_address)
                if not normalized_mac:
                    _LOGGER.warning("Неверный формат MAC адреса в запросе настроек: %s", mac_address)
                    error = InvalidMACAddressError(str(mac_address))
                    return self.json_message(error.translation_key, status_code=400)
                
                device = self.device_manager.get_device_by_mac(normalized_mac)
                identifier = normalized_mac
                identifier_type = "mac"
                
            if not device:
                _LOGGER.debug(
                    "Запрос настроек от неизвестного устройства (MAC: %s, key: %s)",
                    mac_address or "не указан",
                    key or "не указан"
                )
                return self.json_message("Device not found", status_code=404)

            # Получаем настройки устройства через web_server
            if not self.web_server:
                _LOGGER.error("WebServer не инициализирован для получения настроек")
                return self.json_message("Service not available", status_code=503)

            # Проверяем состояние переключателя "Отправить настройки"
            # Если он выключен - возвращаем пустой JSON
            # Используем entity_registry для получения правильного entity_id
            from homeassistant.helpers import entity_registry as er
            registry = er.async_get(self.hass)
            unique_id = f"{device.device_id}_send_settings"
            switch_entity_id = None
            
            # Ищем entity по unique_id
            for entry in registry.entities.values():
                if entry.unique_id == unique_id and entry.platform == "waterius_ha":
                    switch_entity_id = entry.entity_id
                    break
            
            if not switch_entity_id:
                _LOGGER.debug(
                    "Переключатель отправки настроек не найден для устройства %s. "
                    "Возврат пустого JSON.",
                    device.device_id
                )
                # Переключатель не найден - возвращаем пустой JSON
                return self.json({})
            
            # Проверяем состояние переключателя
            switch_state = self.hass.states.get(switch_entity_id)
            
            if not switch_state or switch_state.state != "on":
                _LOGGER.debug(
                    "Переключатель отправки настроек выключен для устройства %s (%s: %s). "
                    "Возврат пустого JSON.",
                    device.device_id,
                    identifier_type,
                    identifier
                )
                # Возвращаем пустой JSON - устройство использует свои текущие настройки
                return self.json({})

            # Переключатель включен - формируем и отправляем настройки
            settings = self.web_server._build_settings_json(device.device_id)
            if not settings:
                _LOGGER.warning(
                    "Не удалось сформировать настройки для устройства %s (%s: %s)",
                    device.device_id,
                    identifier_type,
                    identifier
                )
                # Возвращаем пустой JSON вместо ошибки
                return self.json({})

            _LOGGER.debug(
                "Переключатель включен. Отправка настроек устройству %s (%s: %s)",
                device.device_id,
                identifier_type,
                identifier
            )
            _LOGGER.debug("Настройки для устройства %s: %s", device.device_id, settings)

            # Автоматически выключаем переключатель после возврата настроек
            self.hass.async_create_task(self._turn_off_switch(switch_entity_id))

            # Возвращаем настройки в JSON формате
            return self.json(settings)

        except Exception as e:
            _LOGGER.error("Ошибка при обработке запроса настроек: %s", e, exc_info=True)
            return self.json_message(str(e), status_code=500)

    async def _turn_off_switch(self, entity_id: str) -> None:
        """Автоматическое выключение переключателя после отправки настроек.
        
        Args:
            entity_id: ID переключателя для выключения
        """
        try:
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": entity_id},
                blocking=False,
            )
            _LOGGER.info("Переключатель %s автоматически выключен после отправки настроек", entity_id)
        except Exception as e:
            _LOGGER.warning("Не удалось выключить переключатель %s: %s", entity_id, e)

    def _validate_and_normalize_mac(self, mac_address: str) -> str | None:
        """Валидация и нормализация MAC адреса.
        
        Args:
            mac_address: MAC адрес для валидации
            
        Returns:
            Нормализованный MAC адрес в формате XX:XX:XX:XX:XX:XX или None если невалидный
        """
        if not isinstance(mac_address, str):
            return None
        
        # Удаляем все символы, кроме шестнадцатеричных цифр
        hex_only = "".join(c for c in mac_address.upper() if c in "0123456789ABCDEF")
        
        # Проверяем, что получилось ровно 12 символов
        if len(hex_only) != 12:
            return None
        
        # Форматируем в стандартный вид XX:XX:XX:XX:XX:XX
        normalized = ":".join(hex_only[i:i+2] for i in range(0, 12, 2))
        return normalized


class WateriusWebServer:
    """Веб-сервер для приема данных от Waterius.
    
    Использует стандартные эндпоинты Home Assistant:
    - /api/waterius - для приема данных от устройств
    - /api/waterius/cfg - для получения настроек устройствами
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_manager: DeviceManager | None = None,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Инициализация веб-сервера.

        Args:
            hass: Экземпляр Home Assistant
            device_manager: Менеджер устройств (опционально)
            config_entry: Запись конфигурации (опционально)
        """
        self.hass: HomeAssistant = hass
        self.device_manager: DeviceManager | None = device_manager
        self.config_entry: ConfigEntry | None = config_entry
        # Используем websession из Home Assistant
        self.session = async_get_clientsession(hass)
        self.view: WateriusDataView | None = None
        self.config_view: WateriusConfigView | None = None
        self._setup_routes()
    
    @property
    def auto_add_devices(self) -> bool:
        """Получить текущее значение настройки автодобавления устройств из options."""
        from .const import CONF_AUTO_ADD_DEVICES
        
        if not self.config_entry:
            return True  # По умолчанию включено
        
        # Читаем из options, fallback на data для обратной совместимости
        return self.config_entry.options.get(
            CONF_AUTO_ADD_DEVICES,
            self.config_entry.data.get(CONF_AUTO_ADD_DEVICES, True)
        )

    def _setup_routes(self) -> None:
        """Настройка маршрутов."""
        # Создаем view для использования в основном HTTP сервере Home Assistant
        self.view = WateriusDataView(
            self.hass,
            self.device_manager,
            self.config_entry,
            self,  # Передаем ссылку на web_server
        )
        
        # Создаем view для получения настроек устройствами
        self.config_view = WateriusConfigView(
            self.hass,
            self.device_manager,
            self,  # Передаем ссылку на web_server
        )

    async def start(self) -> None:
        """Запуск веб-сервера (регистрация эндпоинтов в Home Assistant)."""
        # Регистрируем view в основном HTTP сервере Home Assistant
        if self.view:
            self.hass.http.register_view(self.view)
            _LOGGER.info(
                "Зарегистрирован эндпоинт для приема данных от устройств: %s",
                self.view.url,
            )
        
        # Регистрируем view для получения настроек
        if self.config_view:
            self.hass.http.register_view(self.config_view)
            _LOGGER.info(
                "Зарегистрирован эндпоинт для получения настроек устройствами: %s",
                self.config_view.url,
            )
        
        # Регистрируем статический путь для изображений интеграции
        import os
        www_path = os.path.join(os.path.dirname(__file__), "www")
        if os.path.exists(www_path):
            # Проверяем, не зарегистрирован ли уже этот путь
            static_name = f"{DOMAIN}_static"
            existing_route = None
            
            # Ищем существующий роут с таким именем
            for route in self.hass.http.app.router.routes():
                if hasattr(route, 'name') and route.name == static_name:
                    existing_route = route
                    break
            
            # Если роут существует, удаляем его перед добавлением нового
            if existing_route:
                _LOGGER.debug(
                    "Обнаружен существующий статический путь %s, удаляем перед повторной регистрацией",
                    static_name
                )
                try:
                    # Удаляем существующий ресурс из роутера
                    if hasattr(existing_route, '_resource'):
                        self.hass.http.app.router._resources.remove(existing_route._resource)
                except Exception as e:
                    _LOGGER.debug("Не удалось удалить существующий статический путь: %s", e)
            
            try:
                self.hass.http.app.router.add_static(
                    f"/api/{DOMAIN}/static",
                    www_path,
                    name=static_name
                )
                _LOGGER.info(
                    "Зарегистрирован статический путь для изображений: /api/%s/static -> %s",
                    DOMAIN,
                    www_path
                )
            except ValueError as e:
                if "Duplicate" in str(e):
                    _LOGGER.debug(
                        "Статический путь уже зарегистрирован, пропускаем регистрацию: %s",
                        e
                    )
                else:
                    raise
        
        _LOGGER.info("Веб-сервер Waterius успешно запущен на стандартных эндпоинтах Home Assistant")

    async def stop(self) -> None:
        """Остановка веб-сервера (очистка ресурсов)."""
        try:
            # Удаляем статический путь при остановке
            static_name = f"{DOMAIN}_static"
            routes_to_remove = []
            
            # Находим все роуты, связанные с нашей интеграцией
            for route in self.hass.http.app.router.routes():
                if hasattr(route, 'name') and route.name == static_name:
                    routes_to_remove.append(route)
            
            # Удаляем найденные роуты
            for route in routes_to_remove:
                try:
                    if hasattr(route, '_resource'):
                        self.hass.http.app.router._resources.remove(route._resource)
                        _LOGGER.debug("Удален статический путь: %s", static_name)
                except Exception as e:
                    _LOGGER.debug("Не удалось удалить статический путь %s: %s", static_name, e)
            
            # Home Assistant автоматически отменяет регистрацию view при выгрузке интеграции
            _LOGGER.info("Веб-сервер Waterius остановлен")
        except Exception as e:
            _LOGGER.error("Ошибка при остановке веб-сервера: %s", e)
    
    def _build_settings_json(self, device_id: str) -> dict[str, Any] | None:
        """Формирование JSON с настройками для отправки устройству.
        
        ⚡ ВАЖНО: Читает данные из SELECT/NUMBER ENTITIES (желаемое состояние),
        а НЕ из device.data (текущее состояние устройства)!
        
        Args:
            device_id: ID устройства
            
        Returns:
            Словарь с настройками или None если устройство не найдено
        """
        device = self.device_manager.get_device(device_id)
        if not device:
            _LOGGER.warning("Устройство %s не найдено для формирования настроек", device_id)
            return None
        
        # Получаем entity registry для поиска entity по unique_id
        from homeassistant.helpers import entity_registry as er
        registry = er.async_get(self.hass)
        
        # Маппинг: параметр устройства → (unique_id_suffix, domain)
        # unique_id формируется как: {device_id}_{description.key}_config
        entity_mapping = {
            "ctype0": ("channel_0_data_type_config", "select"),  # ⚡ ИЗМЕНЕНО: было counter_type0
            "ctype1": ("channel_1_data_type_config", "select"),  # ⚡ ИЗМЕНЕНО: было counter_type1
            "cname0": ("channel_0_data_type_data_config", "select"),
            "cname1": ("channel_1_data_type_data_config", "select"),
            "factor0": ("channel_0_conversion_factor_config", "select"),
            "factor1": ("channel_1_conversion_factor_config", "select"),
            "wakeup_per_min": ("period_min_config", "number"),
        }
        
        # ✅ Формируем настройки из SELECT/NUMBER ENTITIES (желаемое состояние)
        settings = {}
        
        for device_key, (unique_id_suffix, domain) in entity_mapping.items():
            # Формируем полный unique_id
            unique_id = f"{device_id}_{unique_id_suffix}"
            
            # Ищем entity_id по unique_id через registry
            entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
            
            if not entity_id:
                _LOGGER.debug(
                    "Entity с unique_id=%s не найден в registry для формирования настроек устройства %s",
                    unique_id,
                    device_id
                )
                continue
            
            # Получаем state entity
            state = self.hass.states.get(entity_id)
            
            if not state or state.state in ("unknown", "unavailable"):
                _LOGGER.debug(
                    "Entity %s (unique_id=%s) недоступен для формирования настроек устройства %s (state=%s)",
                    entity_id,
                    unique_id,
                    device_id,
                    state.state if state else "None"
                )
                continue
            
            try:
                # Для select
                if domain == "select":
                    # Для conversion_factor: читаем напрямую из state (уже числовое значение)
                    if device_key in ("factor0", "factor1"):
                        value = int(state.state)
                        settings[device_key] = value
                        _LOGGER.debug(
                            "Из %s получено значение %s=%s (из state)",
                            entity_id,
                            device_key,
                            value
                        )
                    # Для остальных select: читаем internal_value из атрибутов
                    else:
                        value = state.attributes.get("internal_value")
                        if value is not None:
                            settings[device_key] = int(value)
                            _LOGGER.debug(
                                "Из %s получено значение %s=%s (из internal_value)",
                                entity_id,
                                device_key,
                                value
                            )
                        else:
                            _LOGGER.warning(
                                "Не найден internal_value в атрибутах %s (unique_id=%s) для устройства %s",
                                entity_id,
                                unique_id,
                                device_id
                            )
                # Для number: читаем state
                elif domain == "number":
                    value = int(float(state.state))
                    settings[device_key] = value
                    _LOGGER.debug(
                        "Из %s получено значение %s=%s (из state)",
                        entity_id,
                        device_key,
                        value
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "Ошибка преобразования значения %s для %s (unique_id=%s): %s",
                    state.state if state else "None",
                    entity_id,
                    unique_id,
                    e
                )
                continue
        
        if not settings:
            _LOGGER.warning(
                "Не удалось получить настройки из select/number entities для устройства %s",
                device_id
            )
            return None
        
        # Добавляем key устройства для идентификации (из device.data)
        if device.data and "key" in device.data:
            settings["key"] = device.data["key"]
            _LOGGER.debug("Добавлен ключ устройства в настройки: %s", device.data["key"])
        else:
            _LOGGER.warning("Ключ устройства (key) не найден в данных устройства %s", device_id)
        
        _LOGGER.info(
            "✅ Сформированы настройки для устройства %s из SELECT/NUMBER: %s",
            device_id,
            settings
        )
        return settings
