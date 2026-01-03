"""Тесты для validators.py"""
import pytest

from custom_components.waterius_ha.validators import (
    sanitize_string_value,
    validate_device_data,
    sanitize_device_data,
    DANGEROUS_PATTERNS,
    MAX_RSSI_VALUE,
    MIN_RSSI_VALUE,
    MAX_BATTERY_VALUE,
    MIN_BATTERY_VALUE,
    MAX_VOLTAGE_VALUE,
    MIN_VOLTAGE_VALUE,
)
from custom_components.waterius_ha.exceptions import (
    MissingRequiredFieldError,
    InvalidFieldTypeError,
    ValueOutOfRangeError,
)


class TestSanitizeStringValue:
    """Тесты для sanitize_string_value"""

    def test_sanitize_script_tag(self):
        """Тест санитизации <script> тега"""
        value = "<script>alert('xss')</script>"
        result = sanitize_string_value(value)
        assert "&lt;" in result
        assert "&gt;" in result
        assert "<script>" not in result

    def test_sanitize_javascript_protocol(self):
        """Тест санитизации javascript: протокола"""
        value = "javascript:alert('xss')"
        result = sanitize_string_value(value)
        assert "blocked:" in result
        assert "javascript:" not in result

    def test_sanitize_onerror_attribute(self):
        """Тест санитизации onerror= атрибута"""
        value = '<img src=x onerror="alert(1)">'
        result = sanitize_string_value(value)
        assert "&lt;" in result
        assert "&gt;" in result

    def test_sanitize_safe_string(self):
        """Тест что безопасная строка не изменяется"""
        value = "Safe string 123"
        result = sanitize_string_value(value)
        assert result == value

    def test_sanitize_non_string(self):
        """Тест что не-строка возвращается как есть"""
        value = 123
        result = sanitize_string_value(value)
        assert result == value

    def test_sanitize_all_dangerous_patterns(self):
        """Тест всех опасных паттернов"""
        for pattern in DANGEROUS_PATTERNS:
            value = f"test {pattern} test"
            result = sanitize_string_value(value)
            # Должна быть применена санитизация
            assert result != value or pattern not in result.lower()


class TestValidateDeviceData:
    """Тесты для validate_device_data"""

    def test_valid_minimal_data(self):
        """Тест валидации минимальных корректных данных"""
        data = {"mac": "AA:BB:CC:DD:EE:FF"}
        is_valid, errors = validate_device_data(data)
        assert is_valid
        assert len(errors) == 0

    def test_missing_mac_field(self):
        """Тест отсутствия обязательного поля mac"""
        data = {"ch0": 100}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert len(errors) == 1
        assert "mac" in errors[0]

    def test_missing_mac_field_raise_exception(self):
        """Тест выброса исключения при отсутствии mac"""
        data = {"ch0": 100}
        with pytest.raises(MissingRequiredFieldError) as exc_info:
            validate_device_data(data, raise_on_error=True)
        assert exc_info.value.translation_key == "missing_required_field"
        assert exc_info.value.translation_placeholders["field"] == "mac"

    def test_invalid_field_type(self):
        """Тест неверного типа поля"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "rssi": "not_an_int"}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert any("rssi" in error for error in errors)

    def test_invalid_field_type_raise_exception(self):
        """Тест выброса исключения при неверном типе"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "rssi": "not_an_int"}
        with pytest.raises(InvalidFieldTypeError) as exc_info:
            validate_device_data(data, raise_on_error=True)
        assert exc_info.value.translation_key == "invalid_field_type"

    def test_rssi_out_of_range_high(self):
        """Тест RSSI выше допустимого диапазона"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "rssi": MAX_RSSI_VALUE + 10}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert any("RSSI" in error for error in errors)

    def test_rssi_out_of_range_low(self):
        """Тест RSSI ниже допустимого диапазона"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "rssi": MIN_RSSI_VALUE - 10}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert any("RSSI" in error for error in errors)

    def test_rssi_out_of_range_raise_exception(self):
        """Тест выброса исключения при RSSI вне диапазона"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "rssi": MAX_RSSI_VALUE + 10}
        with pytest.raises(ValueOutOfRangeError) as exc_info:
            validate_device_data(data, raise_on_error=True)
        assert exc_info.value.translation_key == "value_out_of_range"
        assert exc_info.value.translation_placeholders["field"] == "rssi"

    def test_battery_out_of_range_high(self):
        """Тест battery выше допустимого диапазона"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "battery": MAX_BATTERY_VALUE + 10}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert any("Battery" in error for error in errors)

    def test_battery_out_of_range_low(self):
        """Тест battery ниже допустимого диапазона"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "battery": MIN_BATTERY_VALUE - 10}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert any("Battery" in error for error in errors)

    def test_voltage_out_of_range_high(self):
        """Тест voltage выше допустимого диапазона"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "voltage": MAX_VOLTAGE_VALUE + 1}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert any("Voltage" in error for error in errors)

    def test_voltage_out_of_range_low(self):
        """Тест voltage ниже допустимого диапазона"""
        data = {"mac": "AA:BB:CC:DD:EE:FF", "voltage": MIN_VOLTAGE_VALUE - 1}
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert any("Voltage" in error for error in errors)

    def test_valid_complete_data(self):
        """Тест валидации полного набора корректных данных"""
        data = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "ch0": 100.5,
            "ch1": 200,
            "delta0": 1.5,
            "delta1": 2,
            "voltage": 3.3,
            "voltage_low": False,
            "voltage_diff": 0.1,
            "battery": 85,
            "rssi": -65,
            "timestamp": "2024-01-01T00:00:00",
            "version": 32,
            "version_esp": "1.1.19",
            "ip": "192.168.1.100",
            "period_min": 30,
            "boot": 1,
            "resets": 0,
            "mode": 3,
            "freemem": 40000,
        }
        is_valid, errors = validate_device_data(data)
        assert is_valid
        assert len(errors) == 0

    def test_sanitize_string_fields(self):
        """Тест санитизации строковых полей"""
        data = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "version_esp": "<script>alert('xss')</script>",
        }
        is_valid, errors = validate_device_data(data)
        # Данные должны быть санитизированы
        assert "&lt;" in data["version_esp"]
        assert "<script>" not in data["version_esp"]

    def test_none_values_allowed(self):
        """Тест что None значения допустимы"""
        data = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "ch0": None,
            "rssi": None,
        }
        is_valid, errors = validate_device_data(data)
        assert is_valid
        assert len(errors) == 0

    def test_not_dict_input(self):
        """Тест что не-словарь возвращает ошибку"""
        data = "not a dict"
        is_valid, errors = validate_device_data(data)
        assert not is_valid
        assert len(errors) > 0

    def test_cname_int_or_str(self):
        """Тест что cname0/cname1 могут быть int или str"""
        data = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "cname0": 5,
            "cname1": "WATER_COLD",
        }
        is_valid, errors = validate_device_data(data)
        assert is_valid

    def test_wifi_phy_mode_int_or_str(self):
        """Тест что wifi_phy_mode может быть int или str"""
        data = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "wifi_phy_mode": 3,
        }
        is_valid, errors = validate_device_data(data)
        assert is_valid

        data["wifi_phy_mode"] = "N"
        is_valid, errors = validate_device_data(data)
        assert is_valid


class TestSanitizeDeviceData:
    """Тесты для sanitize_device_data"""

    def test_sanitize_removes_none_values(self):
        """Тест что None значения удаляются"""
        data = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "ch0": 100,
            "ch1": None,
        }
        result = sanitize_device_data(data)
        assert "mac" in result
        assert "ch0" in result
        assert "ch1" not in result

    def test_sanitize_strips_strings(self):
        """Тест что строки обрезаются (trim)"""
        data = {
            "mac": "  AA:BB:CC:DD:EE:FF  ",
            "version_esp": "  1.1.19  ",
        }
        result = sanitize_device_data(data)
        assert result["mac"] == "AA:BB:CC:DD:EE:FF"
        assert result["version_esp"] == "1.1.19"

    def test_sanitize_preserves_non_strings(self):
        """Тест что не-строки сохраняются"""
        data = {
            "ch0": 100,
            "rssi": -65,
            "voltage_low": False,
        }
        result = sanitize_device_data(data)
        assert result["ch0"] == 100
        assert result["rssi"] == -65
        assert result["voltage_low"] is False

    def test_sanitize_not_dict(self):
        """Тест что не-словарь возвращает пустой словарь"""
        data = "not a dict"
        result = sanitize_device_data(data)
        assert result == {}

    def test_sanitize_empty_dict(self):
        """Тест санитизации пустого словаря"""
        data = {}
        result = sanitize_device_data(data)
        assert result == {}

    def test_sanitize_complete_data(self):
        """Тест санитизации полного набора данных"""
        data = {
            "mac": "  AA:BB:CC:DD:EE:FF  ",
            "ch0": 100,
            "ch1": None,
            "version_esp": "  1.1.19  ",
            "rssi": -65,
        }
        result = sanitize_device_data(data)
        assert result["mac"] == "AA:BB:CC:DD:EE:FF"
        assert result["ch0"] == 100
        assert "ch1" not in result
        assert result["version_esp"] == "1.1.19"
        assert result["rssi"] == -65
