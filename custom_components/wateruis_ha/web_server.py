"""Веб-сервер для приема данных через POST запросы с JSON."""
from __future__ import annotations

import asyncio
import logging
import socket
from aiohttp import web
from typing import Any

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MAC,
    CONF_CHANNEL_0_DATA_TYPE,
    CONF_CHANNEL_1_DATA_TYPE,
)

_LOGGER = logging.getLogger(__name__)


class WateriusWebServer:
    """Веб-сервер для приема данных от Waterius."""

    def __init__(self, hass, port: int, device_manager=None, enable_logging: bool = True, auto_add_devices: bool = False, config_entry=None):
        """Инициализация веб-сервера."""
        self.hass = hass
        self.port = port
        self.device_manager = device_manager
        self.enable_logging = enable_logging
        self.auto_add_devices = auto_add_devices
        self.config_entry = config_entry
        self.app = web.Application()
        self.runner = None
        self.site = None
        self._setup_routes()

    def _setup_routes(self):
        """Настройка маршрутов."""
        # POST маршруты для приема JSON данных
        self.app.router.add_post("/", self.handle_post)
        self.app.router.add_post("/data", self.handle_post)
        self.app.router.add_post("/waterius", self.handle_post)
        # Оставляем GET для обратной совместимости (опционально)
        self.app.router.add_get("/", self.handle_get)
        self.app.router.add_get("/data", self.handle_get)

    async def handle_post(self, request: web.Request) -> web.Response:
        """Обработка POST запросов с JSON данными."""
        try:
            # Получаем JSON данные из тела запроса
            try:
                json_data: dict[str, Any] = await request.json()
            except Exception as e:
                _LOGGER.error("Ошибка при парсинге JSON: %s", e)
                return web.json_response(
                    {"status": "error", "message": "Invalid JSON"}, status=400
                )
            
            # Получаем путь запроса
            path = request.path
            
            # Извлекаем MAC адрес из JSON для идентификации устройства
            mac_address = json_data.get("mac")
            device = None
            device_id = None
            
            if mac_address and self.device_manager:
                # Ищем устройство по MAC адресу
                device = self.device_manager.get_device_by_mac(mac_address)
                if device:
                    device_id = device.device_id
                    _LOGGER.debug(
                        "Найдено устройство %s (%s) по MAC %s",
                        device.name,
                        device_id,
                        mac_address
                    )
                else:
                    # Устройство не найдено - проверяем, нужно ли добавить автоматически
                    if self.auto_add_devices:
                        _LOGGER.info(
                            "Устройство с MAC %s не найдено, пытаемся добавить автоматически...",
                            mac_address
                        )
                        device_id, device_name = await self._auto_add_device(mac_address, json_data)
                        if device_id:
                            device = self.device_manager.get_device(device_id)
                            if device:
                                _LOGGER.info(
                                    "✓ Автоматически добавлено устройство: %s (%s) с MAC %s",
                                    device_name,
                                    device_id,
                                    mac_address
                                )
                            else:
                                _LOGGER.error(
                                    "Устройство %s было добавлено, но не найдено в менеджере",
                                    device_id
                                )
                        else:
                            _LOGGER.warning(
                                "Не удалось автоматически добавить устройство с MAC %s",
                                mac_address
                            )
                    else:
                        _LOGGER.warning(
                            "Устройство с MAC %s не найдено в конфигурации (автоматическое добавление выключено)",
                            mac_address
                        )
            
            _LOGGER.info(
                "Получен POST запрос на %s от устройства %s (MAC: %s)",
                path,
                device_id or "неизвестное",
                mac_address or "не указан"
            )
            
            # Если устройство найдено (или было добавлено), обновляем его данные
            if device and device_id:
                self.device_manager.update_device_data(device_id, json_data)
                
                # Логируем данные в журнал HA, если включено
                if self.enable_logging:
                    self._log_device_data(device.name, device_id, json_data)
                
                # Отправляем событие для конкретного устройства
                self.hass.bus.async_fire(
                    "waterius_device_data_received",
                    {
                        "device_id": device_id,
                        "device_name": device.name,
                        "mac": mac_address,
                        "data": json_data,
                        "remote": str(request.remote) if request.remote else None,
                    }
                )
            else:
                # Логируем данные неизвестного устройства, если включено
                if self.enable_logging:
                    self._log_unknown_device_data(json_data, mac_address)
                
                # Отправляем общее событие, если устройство не найдено
                self.hass.bus.async_fire(
                    "waterius_data_received",
                    {
                        "path": path,
                        "data": json_data,
                        "mac": mac_address,
                        "device_id": device_id,
                        "remote": str(request.remote) if request.remote else None,
                    }
                )
            
            # Возвращаем успешный ответ
            return web.json_response(
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
            return web.json_response(
                {"status": "error", "message": str(e)}, status=500
            )

    async def handle_get(self, request: web.Request) -> web.Response:
        """Обработка GET запросов (для обратной совместимости)."""
        try:
            # Получаем параметры из URL
            query_params = dict(request.query)
            path = request.path
            
            _LOGGER.info(
                "Получен GET запрос на %s с параметрами: %s",
                path,
                query_params
            )
            
            # Отправляем событие в Home Assistant
            self.hass.bus.async_fire(
                "waterius_data_received",
                {
                    "path": path,
                    "query_params": query_params,
                    "remote": str(request.remote) if request.remote else None,
                }
            )
            
            return web.json_response(
                {
                    "status": "ok",
                    "message": "GET запрос получен (используйте POST для отправки JSON)",
                    "path": path,
                }
            )
        except Exception as e:
            _LOGGER.error("Ошибка при обработке GET запроса: %s", e)
            return web.json_response(
                {"status": "error", "message": str(e)}, status=500
            )

    def _is_port_available(self, port: int) -> bool:
        """Проверка доступности порта для прослушивания."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Пытаемся привязать порт - если занят, будет ошибка
                sock.bind(("0.0.0.0", port))
                return True
        except OSError:
            # Порт занят
            return False
        except Exception:
            # Другие ошибки - считаем порт недоступным
            return False

    async def start(self):
        """Запуск веб-сервера."""
        # Проверяем доступность порта перед запуском
        if not self._is_port_available(self.port):
            error_msg = (
                f"Порт {self.port} уже занят. "
                f"Пожалуйста, выберите другой порт в настройках интеграции."
            )
            _LOGGER.error(error_msg)
            raise OSError(f"Port {self.port} is already in use")
        
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(
                self.runner, "0.0.0.0", self.port
            )
            await self.site.start()
            _LOGGER.info("Веб-сервер Waterius запущен на порту %s", self.port)
        except OSError as e:
            if "address in use" in str(e) or e.errno == 98:
                error_msg = (
                    f"Порт {self.port} уже занят другим процессом. "
                    f"Пожалуйста, выберите другой порт в настройках интеграции или "
                    f"остановите процесс, использующий этот порт."
                )
                _LOGGER.error(error_msg)
            else:
                _LOGGER.error("Ошибка при запуске веб-сервера на порту %s: %s", self.port, e)
            raise
        except Exception as e:
            _LOGGER.error("Ошибка при запуске веб-сервера на порту %s: %s", self.port, e)
            raise

    async def stop(self):
        """Остановка веб-сервера."""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            _LOGGER.info("Веб-сервер Waterius остановлен")
        except Exception as e:
            _LOGGER.error("Ошибка при остановке веб-сервера: %s", e)

    def _log_device_data(self, device_name: str, device_id: str, data: dict[str, Any]) -> None:
        """Логирование данных устройства в журнал Home Assistant."""
        try:
            # Формируем сообщение для журнала
            message_parts = [f"Устройство: {device_name}"]
            
            # Добавляем основные параметры
            if "ch0" in data or "ch1" in data:
                ch0 = data.get("ch0", "N/A")
                ch1 = data.get("ch1", "N/A")
                message_parts.append(f"Каналы: CH0={ch0}, CH1={ch1}")
            
            if "delta0" in data or "delta1" in data:
                delta0 = data.get("delta0", "N/A")
                delta1 = data.get("delta1", "N/A")
                message_parts.append(f"Дельта: Δ0={delta0}, Δ1={delta1}")
            
            if "voltage" in data:
                voltage = data.get("voltage")
                voltage_low = data.get("voltage_low", False)
                voltage_status = "⚠ Низкое" if voltage_low else "✓ Норма"
                message_parts.append(f"Напряжение: {voltage}V ({voltage_status})")
            
            if "battery" in data:
                battery = data.get("battery")
                message_parts.append(f"Батарея: {battery}%")
            
            if "timestamp" in data:
                timestamp = data.get("timestamp")
                message_parts.append(f"Время: {timestamp}")
            
            message = " | ".join(message_parts)
            
            # Записываем в журнал через сервис logbook.log
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "logbook",
                    "log",
                    {
                        "name": f"Waterius: {device_name}",
                        "message": message,
                    },
                )
            )
        except Exception as e:
            _LOGGER.error("Ошибка при логировании данных устройства: %s", e)

    def _log_unknown_device_data(self, data: dict[str, Any], mac: str | None) -> None:
        """Логирование данных неизвестного устройства в журнал Home Assistant."""
        try:
            mac_info = f"MAC: {mac}" if mac else "MAC: не указан"
            message = f"Данные от неизвестного устройства ({mac_info})"
            
            # Добавляем основные параметры, если есть
            if "ch0" in data or "ch1" in data:
                ch0 = data.get("ch0", "N/A")
                ch1 = data.get("ch1", "N/A")
                message += f" | Каналы: CH0={ch0}, CH1={ch1}"
            
            # Записываем в журнал
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "logbook",
                    "log",
                    {
                        "name": "Waterius: Неизвестное устройство",
                        "message": message,
                    },
                )
            )
        except Exception as e:
            _LOGGER.error("Ошибка при логировании данных неизвестного устройства: %s", e)

    async def _auto_add_device(self, mac_address: str, json_data: dict[str, Any]) -> tuple[str | None, str | None]:
        """Автоматическое добавление устройства."""
        if not self.device_manager or not self.config_entry:
            return None, None
        
        try:
            # Генерируем device_id на основе MAC адреса
            device_id = f"waterius_{mac_address.replace(':', '_').lower()}"
            
            # Генерируем имя устройства на основе MAC адреса
            # Используем последние 4 символа MAC адреса с символом # перед ними
            mac_short = mac_address.replace(":", "")[-4:].upper()
            device_name = f"Waterius #{mac_short}"
            
            # Проверяем, не существует ли уже устройство с таким ID или MAC
            existing_device = self.device_manager.get_device(device_id)
            if existing_device:
                _LOGGER.warning("Устройство с ID %s уже существует", device_id)
                return None, None
            
            # Проверяем по MAC адресу
            existing_by_mac = self.device_manager.get_device_by_mac(mac_address.upper())
            if existing_by_mac:
                _LOGGER.warning("Устройство с MAC %s уже существует как %s", mac_address, existing_by_mac.device_id)
                return None, None
            
            # Проверяем, нет ли уже устройства с таким MAC в config entry (дополнительная проверка)
            current_devices = self.config_entry.data.get(CONF_DEVICES, [])
            if any(d.get(CONF_DEVICE_MAC, "").upper() == mac_address.upper() for d in current_devices):
                _LOGGER.warning("Устройство с MAC %s уже есть в конфигурации", mac_address)
                return None, None
            
            # Добавляем устройство в менеджер
            if not self.device_manager.add_device(device_id, device_name, mac_address.upper()):
                _LOGGER.error("Не удалось добавить устройство %s в менеджер", device_id)
                return None, None
            
            # Убеждаемся, что устройство добавлено в менеджер
            added_device = self.device_manager.get_device(device_id)
            if not added_device:
                _LOGGER.error("Устройство %s не найдено в менеджере после добавления", device_id)
                return None, None
            
            # Сохраняем устройство в config entry
            new_device = {
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: device_name,
                CONF_DEVICE_MAC: mac_address.upper(),
                CONF_CHANNEL_0_DATA_TYPE: "NOT_USED",
                CONF_CHANNEL_1_DATA_TYPE: "NOT_USED",
            }
            updated_devices = current_devices + [new_device]
            new_data = {**self.config_entry.data, CONF_DEVICES: updated_devices}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            _LOGGER.info(
                "✓ Устройство %s (%s) успешно добавлено и сохранено в конфигурацию",
                device_name,
                device_id
            )
            
            # Отправляем событие для создания sensor entities
            self.hass.bus.async_fire(
                "waterius_device_added",
                {
                    "device_id": device_id,
                    "device_name": device_name,
                    "device_mac": mac_address.upper(),
                    "entry_id": self.config_entry.entry_id,
                }
            )
            
            return device_id, device_name
        except Exception as e:
            _LOGGER.error("Ошибка при автоматическом добавлении устройства: %s", e)
            return None, None

