"""Валидаторы для данных от устройств Waterius."""
from __future__ import annotations

import logging
from typing import Any

from .exceptions import (
    InvalidFieldTypeError,
    MissingRequiredFieldError,
    ValueOutOfRangeError,
)

_LOGGER = logging.getLogger(__name__)

# Константы для валидации
MAX_RSSI_VALUE = 0
MIN_RSSI_VALUE = -120
MAX_BATTERY_VALUE = 100
MIN_BATTERY_VALUE = 0
MAX_VOLTAGE_VALUE = 10.0
MIN_VOLTAGE_VALUE = 0.0

# Опасные паттерны для санитизации строк
DANGEROUS_PATTERNS = ['<script', 'javascript:', 'onerror=', 'onclick=', 'onload=', '<iframe']

# Ожидаемые типы для полей данных устройства
EXPECTED_TYPES: dict[str, type | tuple[type, ...]] = {
    "ch0": (int, float),
    "ch1": (int, float),
    "delta0": (int, float),
    "delta1": (int, float),
    "voltage": (int, float),
    "voltage_low": bool,
    "voltage_diff": (int, float),
    "battery": (int, float),
    "rssi": int,
    "timestamp": str,
    "version": int,
    "version_esp": str,
    "mac": str,
    "ip": str,
    "period_min": int,
    "boot": int,
    "resets": int,
    "mode": int,
    "freemem": int,
    "channel": int,
    "wifi_phy_mode": (int, str),  # Может быть int или str в зависимости от версии прошивки
    "wifi_phy_mode_s": str,
    "router_mac": str,
    "dhcp": bool,
    "email": str,
    "company": str,
    "place": str,
    "esp_id": int,
    "flash_id": int,
    "ntp_errors": int,
    "setup_started": int,
    "setup_finished": int,
    "waketime": int,
    "setuptime": int,
    "period_min_tuned": int,
    "ctype0": int,
    "ctype1": int,
    "cname0": (str, int),  # Может быть str или int в зависимости от версии прошивки
    "cname1": (str, int),  # Может быть str или int в зависимости от версии прошивки
    "data_type0": int,
    "data_type1": int,
    "f0": (int, float),
    "f1": (int, float),
    "imp0": int,
    "imp1": int,
    "adc0": int,
    "adc1": int,
    "ch0_start": (int, float),
    "ch1_start": (int, float),
    "serial0": str,
    "serial1": str,
    "mqtt": bool,
    "ha": bool,
    "http": bool,
    "key": str,
}


def sanitize_string_value(value: str) -> str:
    """Санитизация строкового значения от опасных паттернов.
    
    Args:
        value: Строка для санитизации
        
    Returns:
        Безопасная строка
    """
    if not isinstance(value, str):
        return value
    
    lower_value = value.lower()
    
    # Проверяем на опасные паттерны
    for pattern in DANGEROUS_PATTERNS:
        if pattern in lower_value:
            _LOGGER.warning("Обнаружен опасный паттерн '%s' в данных, применена санитизация", pattern)
            # Экранируем HTML символы
            value = value.replace('<', '&lt;').replace('>', '&gt;')
            value = value.replace('javascript:', 'blocked:')
            break
    
    return value


def validate_device_data(data: dict[str, Any], raise_on_error: bool = False) -> tuple[bool, list[str]]:
    """Валидация данных от устройства с санитизацией.
    
    Args:
        data: Словарь с данными от устройства (модифицируется in-place для санитизации)
        raise_on_error: Выбрасывать исключение при первой ошибке (для переводимых ошибок)
        
    Returns:
        Кортеж (is_valid, list_of_errors)
        
    Raises:
        MissingRequiredFieldError: Если отсутствует обязательное поле (при raise_on_error=True)
        InvalidFieldTypeError: Если тип поля не соответствует ожидаемому (при raise_on_error=True)
        ValueOutOfRangeError: Если значение вне допустимого диапазона (при raise_on_error=True)
    """
    errors: list[str] = []
    
    if not isinstance(data, dict):
        return False, ["Data must be a dictionary"]
    
    # Санитизация строковых полей
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = sanitize_string_value(value)
    
    # Проверяем обязательные поля
    if "mac" not in data:
        if raise_on_error:
            raise MissingRequiredFieldError("mac")
        errors.append("Missing required field: mac")
    
    # Валидируем типы полей
    for key, value in data.items():
        if key in EXPECTED_TYPES:
            expected_type = EXPECTED_TYPES[key]
            # Пропускаем None значения
            if value is None:
                continue
            
            # Проверяем тип
            if isinstance(expected_type, tuple):
                # Множественные допустимые типы
                if not isinstance(value, expected_type):
                    # Для некоторых полей допускаем преобразование типов
                    # Например, cname0/cname1 могут быть int, но мы можем преобразовать в str
                    if key in ("cname0", "cname1") and isinstance(value, (int, str)):
                        continue
                    # wifi_phy_mode может быть int или str
                    elif key == "wifi_phy_mode" and isinstance(value, (int, str)):
                        continue
                    else:
                        expected_str = " | ".join(t.__name__ for t in expected_type)
                        if raise_on_error:
                            raise InvalidFieldTypeError(key, expected_str, type(value).__name__)
                        errors.append(
                            f"Field '{key}' has wrong type: expected {expected_type}, got {type(value).__name__}"
                        )
            else:
                # Один допустимый тип
                if not isinstance(value, expected_type):
                    # Для некоторых полей допускаем преобразование типов
                    if key == "wifi_phy_mode" and isinstance(value, (int, str)):
                        continue
                    elif key in ("cname0", "cname1") and isinstance(value, (int, str)):
                        continue
                    else:
                        if raise_on_error:
                            raise InvalidFieldTypeError(key, expected_type.__name__, type(value).__name__)
                        errors.append(
                            f"Field '{key}' has wrong type: expected {expected_type.__name__}, got {type(value).__name__}"
                        )
    
    # Валидация диапазонов для числовых значений
    if "rssi" in data and isinstance(data["rssi"], (int, float)):
        if data["rssi"] > MAX_RSSI_VALUE or data["rssi"] < MIN_RSSI_VALUE:
            if raise_on_error:
                raise ValueOutOfRangeError(
                    "rssi",
                    str(data["rssi"]),
                    str(MIN_RSSI_VALUE),
                    str(MAX_RSSI_VALUE),
                )
            errors.append(
                f"RSSI value out of range: {data['rssi']} "
                f"(expected {MIN_RSSI_VALUE} to {MAX_RSSI_VALUE})"
            )
    
    if "battery" in data and isinstance(data["battery"], (int, float)):
        if data["battery"] < MIN_BATTERY_VALUE or data["battery"] > MAX_BATTERY_VALUE:
            if raise_on_error:
                raise ValueOutOfRangeError(
                    "battery",
                    str(data["battery"]),
                    str(MIN_BATTERY_VALUE),
                    str(MAX_BATTERY_VALUE),
                )
            errors.append(
                f"Battery value out of range: {data['battery']} "
                f"(expected {MIN_BATTERY_VALUE} to {MAX_BATTERY_VALUE})"
            )
    
    if "voltage" in data and isinstance(data["voltage"], (int, float)):
        if data["voltage"] < MIN_VOLTAGE_VALUE or data["voltage"] > MAX_VOLTAGE_VALUE:
            if raise_on_error:
                raise ValueOutOfRangeError(
                    "voltage",
                    str(data["voltage"]),
                    str(MIN_VOLTAGE_VALUE),
                    str(MAX_VOLTAGE_VALUE),
                )
            errors.append(
                f"Voltage value out of range: {data['voltage']} "
                f"(expected {MIN_VOLTAGE_VALUE} to {MAX_VOLTAGE_VALUE})"
            )
    
    is_valid = len(errors) == 0
    return is_valid, errors


def sanitize_device_data(data: dict[str, Any]) -> dict[str, Any]:
    """Очистка и нормализация данных от устройства.
    
    Args:
        data: Словарь с данными от устройства
        
    Returns:
        Очищенный словарь с данными
    """
    if not isinstance(data, dict):
        return {}
    
    sanitized: dict[str, Any] = {}
    
    for key, value in data.items():
        # Пропускаем None значения
        if value is None:
            continue
        
        # Нормализуем строки (убираем лишние пробелы)
        if isinstance(value, str):
            sanitized[key] = value.strip()
        else:
            sanitized[key] = value
    
    return sanitized

