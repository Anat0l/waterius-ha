"""Константы для интеграции Waterius."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "waterius_ha"

CONF_DEVICES: Final = "devices"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_DEVICE_MAC: Final = "device_mac"
CONF_DEVICE_KEY: Final = "device_key"  # Серийный номер устройства
CONF_AUTO_ADD_DEVICES: Final = "auto_add_devices"

# Константы устройства
DEVICE_MANUFACTURER: Final = "Waterius"
DEVICE_MODEL: Final = "Classic"
DEVICE_HW_VERSION: Final = "1.0.0"

# Константы для веб-сервера
MAX_JSON_SIZE: Final = 5 * 1024  # Максимальный размер JSON в байтах (5 КБайт)

# Опции для типа канала (counter_type0/counter_type1)
# ⚠️ ВАЖНО: Согласно протоколу устройства Waterius: enum CounterType
# Структура: (название_опции, числовое_значение)
_CHANNEL_TYPE_DATA: Final[tuple[tuple[str, int], ...]] = (
    ("mechanic", 0),      # Механический (DISCRETE в прошивке) ⚡ ИСПРАВЛЕНО: было 1
    ("electronic", 2),    # Электронный (ELECTRONIC)
    ("not_used", 255),    # Не используется / Выключен (NONE = 0xFF)
)

# Автоматически генерируемые константы из структуры данных
CHANNEL_TYPE_OPTIONS: Final[list[str]] = [name for name, _ in _CHANNEL_TYPE_DATA]
CHANNEL_TYPE_MECHANIC: Final = 0      # ⚡ ИСПРАВЛЕНО: было 1, теперь 0
CHANNEL_TYPE_ELECTRONIC: Final = 2    # Для обратной совместимости
CHANNEL_TYPE_NOT_USED: Final = 255    # Для обратной совместимости

# Маппинги для быстрого преобразования
_CHANNEL_TYPE_TO_VALUE: Final[dict[str, int]] = {name: value for name, value in _CHANNEL_TYPE_DATA}
_VALUE_TO_CHANNEL_TYPE: Final[dict[int, str]] = {value: name for name, value in _CHANNEL_TYPE_DATA}

# Опции для типа данных канала (data_type)
# ⚠️ ВАЖНО: enum CounterName из прошивки Waterius (для cname0/cname1)
# Это ПОСЛЕДОВАТЕЛЬНЫЙ список 0-7
_COUNTER_NAME_DATA: Final[tuple[tuple[str, int], ...]] = (
    ("water_cold", 0),      # Холодная вода
    ("water_hot", 1),       # Горячая вода
    ("electro", 2),         # Электроэнергия
    ("gas", 3),             # Газ
    ("heat_gcal", 4),       # Тепло (Гкал)
    ("portable_water", 5),  # Питьевая вода
    ("other", 6),           # Другое
    ("heat_kwt", 7),        # Тепло (кВт)
)

# Генерируем список опций и словари для конвертации CounterName (cname0/cname1)
COUNTER_NAME_OPTIONS: Final[list[str]] = [name for name, _ in _COUNTER_NAME_DATA]
_COUNTER_NAME_TO_VALUE: Final[dict[str, int]] = {name: value for name, value in _COUNTER_NAME_DATA}
_VALUE_TO_COUNTER_NAME: Final[dict[int, str]] = {value: name for name, value in _COUNTER_NAME_DATA}
COUNTER_NAME_OTHER: Final = 6  # OTHER для CounterName

# Опции для коэффициента пересчета (f0, f1)
CONVERSION_FACTOR_OPTIONS: Final[list[str]] = ["1", "10", "100"]


# ===============================================
# Helper функции для преобразования значений
# ===============================================

def convert_channel_type_to_value(option: str) -> int:
    """Преобразование строковой опции типа канала в числовое значение.
    
    Args:
        option: Внутренняя опция (MECHANIC, ELECTRONIC, NOT_USED)
        
    Returns:
        Числовое значение согласно протоколу устройства
    """
    return _CHANNEL_TYPE_TO_VALUE.get(option, CHANNEL_TYPE_NOT_USED)


def convert_value_to_channel_type(value: int | float | str | None) -> str:
    """Преобразование числового значения в строковую опцию типа канала.
    
    Args:
        value: Числовое значение от устройства
        
    Returns:
        Внутренняя опция (MECHANIC, ELECTRONIC, NOT_USED)
    """
    try:
        value_int = int(float(value)) if value is not None else None
    except (ValueError, TypeError):
        return "not_used"
    
    if value_int is None:
        return "not_used"
    
    return _VALUE_TO_CHANNEL_TYPE.get(value_int, "not_used")


def convert_counter_name_to_value(option: str) -> int:
    """Преобразование опции CounterName (cname) в числовое значение.
    
    Args:
        option: Опция из COUNTER_NAME_OPTIONS (например, "WATER_COLD")
        
    Returns:
        Числовое значение для устройства (0-7)
    """
    return _COUNTER_NAME_TO_VALUE.get(option, COUNTER_NAME_OTHER)


def convert_value_to_counter_name(value: int | float | str | None) -> str:
    """Преобразование числового значения в опцию CounterName (cname).
    
    Args:
        value: Числовое значение от устройства (0-7)
        
    Returns:
        Опция из COUNTER_NAME_OPTIONS (например, "WATER_COLD")
    """
    try:
        value_int = int(float(value)) if value is not None else None
    except (ValueError, TypeError):
        return "OTHER"
    
    if value_int is None:
        return "OTHER"
    
    return _VALUE_TO_COUNTER_NAME.get(value_int, "OTHER")

