"""Исключения для интеграции Waterius с поддержкой переводов."""
from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class WateriusError(HomeAssistantError):
    """Базовое исключение для интеграции Waterius."""


class WateriusValidationError(WateriusError):
    """Ошибка валидации данных от устройства."""
    
    def __init__(
        self,
        translation_key: str,
        translation_placeholders: dict[str, str] | None = None,
    ) -> None:
        """Initialize validation error.
        
        Args:
            translation_key: Ключ для перевода сообщения об ошибке
            translation_placeholders: Плейсхолдеры для перевода
        """
        super().__init__(translation_key)
        self.translation_domain = "waterius_ha"
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders or {}


class InvalidMACAddressError(WateriusValidationError):
    """Недопустимый MAC адрес."""
    
    def __init__(self, mac: str) -> None:
        """Initialize with MAC address.
        
        Args:
            mac: Недопустимый MAC адрес
        """
        super().__init__(
            translation_key="invalid_mac_address",
            translation_placeholders={"mac": mac},
        )


class MissingRequiredFieldError(WateriusValidationError):
    """Отсутствует обязательное поле."""
    
    def __init__(self, field: str) -> None:
        """Initialize with field name.
        
        Args:
            field: Название отсутствующего поля
        """
        super().__init__(
            translation_key="missing_required_field",
            translation_placeholders={"field": field},
        )


class InvalidFieldTypeError(WateriusValidationError):
    """Недопустимый тип поля."""
    
    def __init__(self, field: str, expected: str, got: str) -> None:
        """Initialize with field type information.
        
        Args:
            field: Название поля
            expected: Ожидаемый тип
            got: Полученный тип
        """
        super().__init__(
            translation_key="invalid_field_type",
            translation_placeholders={
                "field": field,
                "expected": expected,
                "got": got,
            },
        )


class ValueOutOfRangeError(WateriusValidationError):
    """Значение вне допустимого диапазона."""
    
    def __init__(
        self,
        field: str,
        value: str,
        min_value: str,
        max_value: str,
    ) -> None:
        """Initialize with range information.
        
        Args:
            field: Название поля
            value: Текущее значение
            min_value: Минимальное допустимое значение
            max_value: Максимальное допустимое значение
        """
        super().__init__(
            translation_key="value_out_of_range",
            translation_placeholders={
                "field": field,
                "value": value,
                "min": min_value,
                "max": max_value,
            },
        )


class InvalidEncodingError(WateriusError):
    """Недопустимая кодировка данных."""
    
    def __init__(self) -> None:
        """Initialize encoding error."""
        super().__init__("invalid_encoding")
        self.translation_domain = "waterius_ha"
        self.translation_key = "invalid_encoding"
        self.translation_placeholders: dict[str, str] = {}


class InvalidJSONError(WateriusError):
    """Недопустимый JSON."""
    
    def __init__(self) -> None:
        """Initialize JSON error."""
        super().__init__("invalid_json")
        self.translation_domain = "waterius_ha"
        self.translation_key = "invalid_json"
        self.translation_placeholders: dict[str, str] = {}


class InvalidRequestError(WateriusError):
    """Недопустимый запрос."""
    
    def __init__(self) -> None:
        """Initialize request error."""
        super().__init__("invalid_request")
        self.translation_domain = "waterius_ha"
        self.translation_key = "invalid_request"
        self.translation_placeholders: dict[str, str] = {}


class ZeroconfAddressError(WateriusError):
    """Ошибка получения IPv4 адресов для Zeroconf."""
    
    def __init__(self) -> None:
        """Initialize Zeroconf address error."""
        super().__init__("zeroconf_no_ipv4")
        self.translation_domain = "waterius_ha"
        self.translation_key = "zeroconf_no_ipv4"
        self.translation_placeholders: dict[str, str] = {}


class ZeroconfConversionError(WateriusError):
    """Ошибка преобразования адресов для Zeroconf."""
    
    def __init__(self) -> None:
        """Initialize Zeroconf conversion error."""
        super().__init__("zeroconf_conversion_failed")
        self.translation_domain = "waterius_ha"
        self.translation_key = "zeroconf_conversion_failed"
        self.translation_placeholders: dict[str, str] = {}
