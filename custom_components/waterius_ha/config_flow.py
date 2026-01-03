"""Config flow для интеграции Waterius."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_AUTO_ADD_DEVICES,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Валидация входных данных."""
    return {"title": "Waterius"}


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
        
        # Создаем интеграцию без дополнительной настройки
        # Использует стандартные эндпоинты Home Assistant: /api/waterius и /api/waterius/cfg
        info = await validate_input(self.hass, {})
        
        # data содержит только неизменяемые данные (список устройств изменяется программно)
        data: dict[str, Any] = {
            CONF_DEVICES: [],
        }
        
        # options содержит пользовательские настройки
        options = {
            CONF_AUTO_ADD_DEVICES: True,  # Автоматическое добавление устройств по умолчанию включено
        }
        
        return self.async_create_entry(title=info["title"], data=data, options=options)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Обработка reconfigure flow."""
        config_entry = self._get_reconfigure_entry()
        
        # Нечего перенастраивать - интеграция работает автоматически
        info = await validate_input(self.hass, {})
        
        return self.async_update_reload_and_abort(
            config_entry,
            reason="reconfigure_successful",
            title=info["title"],
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Создание options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Обработка options flow для Waterius."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Управление настройками."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Схема с описанием полей через data_description
        # self.config_entry доступен автоматически из родительского класса
        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AUTO_ADD_DEVICES,
                    default=self.config_entry.options.get(CONF_AUTO_ADD_DEVICES, True),
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
