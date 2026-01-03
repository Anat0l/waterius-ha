# Dependencies

This integration uses the following external dependencies:

## Required Dependencies

### aiohttp (>=3.8.0)
- **Purpose**: Asynchronous HTTP client/server framework
- **Usage**: Used for handling HTTP POST requests from Waterius devices and making HTTP requests to devices
- **License**: Apache License 2.0
- **Repository**: https://github.com/aio-libs/aiohttp
- **Documentation**: https://docs.aiohttp.org/
- **PyPI**: https://pypi.org/project/aiohttp/

**Why this version?**
- Version 3.8.0+ provides improved async/await support
- Better WebSocket handling
- Enhanced security features
- Required for proper integration with Home Assistant's HTTP component

## Home Assistant Dependencies

This integration depends on the following Home Assistant components:

### http
- **Purpose**: Home Assistant HTTP component
- **Usage**: Registering HTTP views for receiving data from devices
- **Type**: Core component

### zeroconf
- **Purpose**: Zero-configuration networking (mDNS/DNS-SD)
- **Usage**: Announcing the integration service on the local network for device discovery
- **Type**: Core component

## Development Dependencies

For development and testing, the following dependencies are recommended:

### pytest
- **Purpose**: Testing framework
- **Repository**: https://github.com/pytest-dev/pytest
- **PyPI**: https://pypi.org/project/pytest/

### pytest-homeassistant-custom-component
- **Purpose**: Home Assistant custom component testing utilities
- **Repository**: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
- **PyPI**: https://pypi.org/project/pytest-homeassistant-custom-component/

### mypy (>=1.8.0)
- **Purpose**: Static type checker with strict mode
- **Usage**: Type checking all integration code with strict configuration
- **Repository**: https://github.com/python/mypy
- **Documentation**: https://mypy.readthedocs.io/
- **PyPI**: https://pypi.org/project/mypy/

**Configuration:**
- Strict mode enabled in `mypy.ini`
- All functions require type annotations
- PEP 561 compliant with `py.typed` marker
- See [STRICT_TYPING.md](STRICT_TYPING.md) for details

## Security Considerations

### Input Validation
- All incoming data is validated using custom validators in `validators.py`
- Maximum JSON size limit enforced (5KB)
- String sanitization to prevent injection attacks
- Type checking for all data fields

### Network Security
- Local network only (no cloud dependencies)
- Uses standard HTTP (device limitation)
- Data validation on all endpoints

## Version Compatibility

| Dependency | Minimum Version | Tested Version | Notes |
|------------|----------------|----------------|-------|
| aiohttp | 3.8.0 | 3.9.x | Latest stable recommended |
| Home Assistant | 2023.x | 2024.x | Tested with recent versions |
| Python | 3.11 | 3.12 | Home Assistant requirement |

## Dependency Updates

When updating dependencies:
1. Check for breaking changes in changelogs
2. Update version constraint in `manifest.json`
3. Run full test suite
4. Update this document with new version information
5. Test with actual Waterius devices

## License Compliance

All dependencies are compatible with the Apache License 2.0 used by this integration:

- **aiohttp**: Apache License 2.0 ✅

No GPL or other restrictive licenses are used.

## Minimal Dependencies Philosophy

This integration intentionally keeps dependencies minimal:
- ✅ Only one external dependency (aiohttp)
- ✅ No cloud service dependencies
- ✅ No database dependencies
- ✅ All data processing done locally
- ✅ Uses Home Assistant's built-in components where possible

## Future Dependencies

Potential future additions (not currently required):

### None planned
The integration is designed to remain lightweight with minimal dependencies. Any future additions will be carefully evaluated for necessity and security.

---

**Last Updated**: January 2026
**Integration Version**: 1.0.0

