"""Config flow для интеграции Waterius."""
from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.translation import async_get_translations

from .const import (
    DOMAIN,
    CONF_PORT,
    DEFAULT_PORT,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_ENABLE_LOGGING,
    DEFAULT_ENABLE_LOGGING,
    CONF_AUTO_ADD_DEVICES,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1024, max=65535)
        ),
        vol.Required(CONF_ENABLE_LOGGING, default=DEFAULT_ENABLE_LOGGING): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Валидация входных данных."""
    port = data[CONF_PORT]
    
    # Проверка доступности порта для прослушивания
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Пытаемся привязать порт - если занят, будет ошибка
            sock.bind(("0.0.0.0", port))
    except OSError:
        # Порт занят
        raise InvalidPort(f"Порт {port} уже занят. Выберите другой порт.")
    except Exception as e:
        _LOGGER.warning("Не удалось проверить доступность порта %s: %s", port, e)
        # Продолжаем, так как проверка может не сработать в некоторых случаях
    
    return {"title": f"Waterius на порту {port}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Обработка config flow для Waterius."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Обработка шага пользователя."""
        # Проверяем, что интеграция еще не настроена
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidPort:
                errors["base"] = "invalid_port"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Инициализируем пустой список устройств
                user_input[CONF_DEVICES] = []
                # Автоматическое добавление устройств всегда включено
                user_input[CONF_AUTO_ADD_DEVICES] = True
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        """Получение options flow handler."""
        return OptionsFlowHandler()


class InvalidPort(HomeAssistantError):
    """Неверный порт."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Обработчик options flow для управления устройствами."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Инициализация options flow."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Получаем текущий порт
            current_port = self.config_entry.data.get(CONF_PORT, DEFAULT_PORT)
            new_port = user_input.get(CONF_PORT)
            
            # Валидация порта только если он изменился
            if new_port and new_port != current_port:
                try:
                    # Проверяем доступность порта
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind(("0.0.0.0", new_port))
                except OSError:
                    errors["base"] = "invalid_port"
                except Exception as e:
                    _LOGGER.warning("Не удалось проверить доступность порта %s: %s", new_port, e)
            
            if not errors:
                # Получаем текущие данные
                current_data = self.config_entry.data.copy()
                
                # Обновляем порт и enable_logging
                port_changed = False
                if CONF_PORT in user_input:
                    new_port = user_input[CONF_PORT]
                    if new_port != current_data.get(CONF_PORT):
                        current_data[CONF_PORT] = new_port
                        port_changed = True
                
                if CONF_ENABLE_LOGGING in user_input:
                    current_data[CONF_ENABLE_LOGGING] = user_input[CONF_ENABLE_LOGGING]
                
                # Обработка удаления устройств
                devices = current_data.get(CONF_DEVICES, [])
                devices_to_remove = user_input.get("devices_to_remove", [])
                
                if devices_to_remove:
                    updated_devices = []
                    for device in devices:
                        device_id = device.get(CONF_DEVICE_ID)
                        if device_id not in devices_to_remove:
                            updated_devices.append(device)
                    
                    current_data[CONF_DEVICES] = updated_devices
                    
                    # Удаляем устройства из device_manager
                    if self.config_entry.entry_id in self.hass.data.get(DOMAIN, {}):
                        entry_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
                        device_manager = entry_data.get("device_manager")
                        if device_manager:
                            for device_id in devices_to_remove:
                                device_manager.remove_device(device_id)
                                # Удаляем device из device registry
                                dev_reg = dr.async_get(self.hass)
                                device_entry = dev_reg.async_get_device(
                                    identifiers={(DOMAIN, device_id)}
                                )
                                if device_entry:
                                    dev_reg.async_remove_device(device_entry.id)
                    
                    _LOGGER.info("Удалено устройств: %d", len(devices_to_remove))
                
                # Обновляем config entry
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=current_data
                )
                
                # Если изменился порт, перезагружаем интеграцию после сохранения
                if port_changed:
                    _LOGGER.info("Порт изменен на %s, перезагружаем интеграцию", new_port)
                    # Планируем перезагрузку после завершения flow
                    self.hass.async_create_task(
                        self._reload_after_save()
                    )
                
                return self.async_create_entry(title="", data={})
    
        # Получаем текущие значения
        current_port = self.config_entry.data.get(CONF_PORT, DEFAULT_PORT)
        current_enable_logging = self.config_entry.data.get(CONF_ENABLE_LOGGING, DEFAULT_ENABLE_LOGGING)
        devices = self.config_entry.data.get(CONF_DEVICES, [])
        
        # Формируем схему
        # Для options flow Home Assistant применяет переводы из options.step.init.data
        # на основе ключей в схеме (CONF_PORT, CONF_ENABLE_LOGGING, devices_to_remove)
        schema_fields = {
            vol.Required(CONF_PORT, default=current_port): vol.All(
                vol.Coerce(int), vol.Range(min=1024, max=65535)
            ),
            vol.Required(CONF_ENABLE_LOGGING, default=current_enable_logging): bool,
        }
        
        # Добавляем поле для удаления устройств, если есть устройства
        if devices:
            # Получаем переводы для строки "Unknown"
            try:
                translations = await async_get_translations(
                    self.hass, self.hass.config.language, "config", [DOMAIN]
                )
                unknown_device = translations.get(
                    f"{DOMAIN}::config::options::unknown_device", 
                    "Unknown Device"
                )
            except Exception:
                # Если не удалось получить переводы, используем значение по умолчанию
                unknown_device = "Unknown Device"
            
            device_options = {
                d.get(CONF_DEVICE_ID): f"{d.get(CONF_DEVICE_NAME, unknown_device)} ({d.get(CONF_DEVICE_ID)})"
                for d in devices
            }
            schema_fields[vol.Optional("devices_to_remove", default=[])] = vol.All(
                cv.multi_select(device_options),
            )
        
        schema = vol.Schema(schema_fields)
        
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
    
    async def _reload_after_save(self) -> None:
        """Перезагрузка интеграции после сохранения изменений."""
        # Небольшая задержка, чтобы убедиться, что entry обновлен
        await asyncio.sleep(0.2)
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
