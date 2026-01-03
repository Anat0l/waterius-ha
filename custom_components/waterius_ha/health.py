"""Модуль для проверки здоровья интеграции и создания repair issues."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

if TYPE_CHECKING:
    from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)

# Время без обновлений для создания repair issue (24 часа)
DEVICE_NO_RESPONSE_THRESHOLD = timedelta(hours=24)


@callback
def async_create_device_no_response_issue(
    hass: HomeAssistant,
    device_id: str,
    device_name: str,
    hours_without_update: int,
) -> None:
    """Создание repair issue для устройства, которое не отвечает."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"device_no_response_{device_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="device_no_response",
        translation_placeholders={
            "device_id": device_id,
            "device_name": device_name,
            "hours": str(hours_without_update),
        },
        data={"device_id": device_id},
    )


@callback
def async_delete_device_no_response_issue(
    hass: HomeAssistant,
    device_id: str,
) -> None:
    """Удаление repair issue для устройства, которое не отвечает."""
    ir.async_delete_issue(hass, DOMAIN, f"device_no_response_{device_id}")


async def async_check_integration_health(
    hass: HomeAssistant,
    entry_id: str,
    device_manager: DeviceManager | None = None,
) -> None:
    """Проверка состояния интеграции и создание repair issues при необходимости."""
    # Проверка устройств на неотвечающие
    if device_manager:
        now = datetime.now()
        for device_id, device in device_manager.get_all_devices().items():
            if device.last_update_time:
                time_since_update = now - device.last_update_time
                if time_since_update > DEVICE_NO_RESPONSE_THRESHOLD:
                    hours_without_update = int(time_since_update.total_seconds() / 3600)
                    async_create_device_no_response_issue(
                        hass,
                        device_id,
                        device.name,
                        hours_without_update,
                    )
                else:
                    async_delete_device_no_response_issue(hass, device_id)
            else:
                # Если устройство никогда не обновлялось, но было добавлено более 24 часов назад
                # Это сложнее отследить, поэтому пропускаем такие случаи
                pass

