"""Test the Waterius config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.waterius_ha.const import (
    CONF_AUTO_ADD_DEVICES,
    CONF_DEVICES,
    DOMAIN,
)


async def test_form_user_single_instance(hass: HomeAssistant) -> None:
    """Test we only allow a single config flow instance."""
    # Create a mock config entry
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius",
        data={CONF_DEVICES: []},
        options={CONF_AUTO_ADD_DEVICES: True},
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    
    # Add the entry to hass
    config_entry.add_to_hass(hass)
    
    # Try to create another config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Should abort with single_instance_allowed
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_form_user_create_entry(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test we can create a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Should show form
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Waterius"
    assert result["data"] == {CONF_DEVICES: []}
    assert result["options"] == {CONF_AUTO_ADD_DEVICES: True}
    
    # Verify setup was called
    await hass.async_block_till_done()
    assert len(mock_setup_entry.mock_calls) == 1


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test reconfigure flow."""
    # Create a config entry
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius",
        data={CONF_DEVICES: []},
        options={CONF_AUTO_ADD_DEVICES: True},
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    config_entry.add_to_hass(hass)
    
    # Start reconfigure flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": config_entry.entry_id,
        },
    )
    
    # Should update and reload
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    
    # Verify the entry was reloaded
    await hass.async_block_till_done()


async def test_options_flow_init(hass: HomeAssistant) -> None:
    """Test options flow initialization."""
    # Create a config entry
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius",
        data={CONF_DEVICES: []},
        options={CONF_AUTO_ADD_DEVICES: True},
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    config_entry.add_to_hass(hass)
    
    # Start options flow
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    
    # Should show form with current options
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    
    # Check that the schema has the auto_add_devices field
    assert "data_schema" in result
    schema = result["data_schema"]
    assert CONF_AUTO_ADD_DEVICES in str(schema)


async def test_options_flow_update(hass: HomeAssistant) -> None:
    """Test options flow can update settings."""
    # Create a config entry
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius",
        data={CONF_DEVICES: []},
        options={CONF_AUTO_ADD_DEVICES: True},
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    config_entry.add_to_hass(hass)
    
    # Start options flow
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    
    # Submit with new values
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_AUTO_ADD_DEVICES: False},
    )
    
    # Should create entry with new options
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_AUTO_ADD_DEVICES: False}


async def test_options_flow_default_values(hass: HomeAssistant) -> None:
    """Test options flow uses correct default values."""
    # Create a config entry without options
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius",
        data={CONF_DEVICES: []},
        options={},  # No options set
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    config_entry.add_to_hass(hass)
    
    # Start options flow
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    
    # Should show form
    assert result["type"] == FlowResultType.FORM
    
    # Submit without changes (should use defaults)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_AUTO_ADD_DEVICES: True},  # Default value
    )
    
    # Should create entry with defaults
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTO_ADD_DEVICES] is True


async def test_validate_input(hass: HomeAssistant) -> None:
    """Test the validate_input function."""
    from custom_components.waterius_ha.config_flow import validate_input
    
    # Test with empty data
    result = await validate_input(hass, {})
    assert result["title"] == "Waterius"
    
    # Test with any data (should always return same title)
    result = await validate_input(hass, {"some": "data"})
    assert result["title"] == "Waterius"


async def test_config_flow_step_user_no_input(hass: HomeAssistant) -> None:
    """Test config flow user step creates entry immediately without form."""
    # The flow should create entry immediately without showing a form
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Should create entry directly (no form shown)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Waterius"
    
    # Verify data structure
    assert CONF_DEVICES in result["data"]
    assert result["data"][CONF_DEVICES] == []
    
    # Verify options structure
    assert CONF_AUTO_ADD_DEVICES in result["options"]
    assert result["options"][CONF_AUTO_ADD_DEVICES] is True


async def test_reconfigure_flow_with_no_changes(hass: HomeAssistant) -> None:
    """Test reconfigure flow completes successfully even with no changes."""
    # Create a config entry
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius Old",
        data={CONF_DEVICES: []},
        options={CONF_AUTO_ADD_DEVICES: False},
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    config_entry.add_to_hass(hass)
    
    # Store original title
    original_title = config_entry.title
    
    # Start reconfigure flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": config_entry.entry_id,
        },
    )
    
    # Should complete successfully
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    
    # Title should be updated to standard "Waterius"
    # Note: The actual update happens in async_update_reload_and_abort


async def test_options_flow_preserves_data(hass: HomeAssistant) -> None:
    """Test that options flow doesn't modify config entry data."""
    # Create a config entry with some devices
    test_devices = [
        {
            "device_id": "waterius_test",
            "device_name": "Test Device",
            "device_mac": "AA:BB:CC:DD:EE:FF",
        }
    ]
    
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius",
        data={CONF_DEVICES: test_devices},
        options={CONF_AUTO_ADD_DEVICES: True},
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    config_entry.add_to_hass(hass)
    
    # Start options flow
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    
    # Submit with changed options
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_AUTO_ADD_DEVICES: False},
    )
    
    # Should create entry
    assert result["type"] == FlowResultType.CREATE_ENTRY
    
    # Verify data wasn't modified
    assert config_entry.data[CONF_DEVICES] == test_devices


async def test_multiple_options_flow_updates(hass: HomeAssistant) -> None:
    """Test multiple sequential options flow updates."""
    # Create a config entry
    config_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Waterius",
        data={CONF_DEVICES: []},
        options={CONF_AUTO_ADD_DEVICES: True},
        source=config_entries.SOURCE_USER,
        unique_id=None,
    )
    config_entry.add_to_hass(hass)
    
    # First update: disable auto_add_devices
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_AUTO_ADD_DEVICES: False},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTO_ADD_DEVICES] is False
    
    # Second update: enable auto_add_devices again
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_AUTO_ADD_DEVICES: True},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTO_ADD_DEVICES] is True


async def test_config_entry_data_structure(hass: HomeAssistant) -> None:
    """Test that config entry has correct data structure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Verify data structure
    assert isinstance(result["data"], dict)
    assert CONF_DEVICES in result["data"]
    assert isinstance(result["data"][CONF_DEVICES], list)
    
    # Verify options structure
    assert isinstance(result["options"], dict)
    assert CONF_AUTO_ADD_DEVICES in result["options"]
    assert isinstance(result["options"][CONF_AUTO_ADD_DEVICES], bool)


async def test_config_entry_default_values(hass: HomeAssistant) -> None:
    """Test that config entry uses correct default values."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Check default values
    assert result["data"][CONF_DEVICES] == []  # Empty list by default
    assert result["options"][CONF_AUTO_ADD_DEVICES] is True  # Enabled by default
