# Тесты для интеграции Waterius

## 📋 Содержание

- [Установка зависимостей](#установка-зависимостей)
- [Запуск тестов](#запуск-тестов)
- [Структура тестов](#структура-тестов)
- [Покрытие тестами](#покрытие-тестами)

## 🔧 Установка зависимостей

### Установка тестовых зависимостей

```bash
# Установка всех зависимостей для тестирования
pip install -r requirements-test.txt

# Или только pytest и необходимые пакеты
pip install pytest pytest-asyncio pytest-homeassistant-custom-component
```

### Установка для разработки

```bash
# Установка в режиме разработки
pip install -e .
pip install -r requirements.txt
pip install -r requirements-test.txt
```

## 🚀 Запуск тестов

### Запуск всех тестов

```bash
# Linux/Mac
./run_tests.sh

# Windows PowerShell
.\run_tests.ps1

# Или напрямую через pytest
pytest tests/
```

### Запуск конкретного файла тестов

```bash
# Тесты config flow
pytest tests/test_config_flow.py

# С подробным выводом
pytest tests/test_config_flow.py -v

# С трассировкой ошибок
pytest tests/test_config_flow.py -v --tb=long
```

### Запуск конкретного теста

```bash
# Запустить один тест
pytest tests/test_config_flow.py::test_form_user_create_entry

# С подробным выводом
pytest tests/test_config_flow.py::test_form_user_create_entry -v -s
```

### Запуск с покрытием кода

```bash
# С отчетом о покрытии
pytest tests/ --cov=custom_components.waterius_ha --cov-report=term-missing

# С HTML отчетом
pytest tests/ --cov=custom_components.waterius_ha --cov-report=html

# Открыть HTML отчет (создается в htmlcov/index.html)
# Linux/Mac
open htmlcov/index.html

# Windows
start htmlcov/index.html
```

### Параллельный запуск тестов

```bash
# Запуск тестов в 4 потока
pytest tests/ -n 4

# Автоматическое определение количества процессоров
pytest tests/ -n auto
```

## 📁 Структура тестов

```
tests/
├── __init__.py              # Инициализация тестового пакета
├── conftest.py              # Общие фикстуры для всех тестов
├── test_config_flow.py      # Тесты для config flow
└── README.md                # Эта документация
```

### Описание файлов

- **`__init__.py`** - Делает tests директорию Python пакетом
- **`conftest.py`** - Содержит общие pytest фикстуры:
  - `auto_enable_custom_integrations` - автоматически включает кастомные интеграции
  - `mock_setup_entry` - мокает async_setup_entry
  - `mock_device_manager` - мокает DeviceManager
  - `mock_web_server` - мокает WateriusWebServer

- **`test_config_flow.py`** - Тесты для config flow:
  - Тестирование создания config entry
  - Тестирование single instance
  - Тестирование reconfigure flow
  - Тестирование options flow
  - Тестирование валидации
  - Тестирование структуры данных

## 📊 Покрытие тестами

### Текущее покрытие

**Config Flow:** ✅ 100% - Полное покрытие

Тесты покрывают:
- ✅ Создание config entry через user flow
- ✅ Проверка single instance (только одна интеграция)
- ✅ Reconfigure flow
- ✅ Options flow (создание и обновление)
- ✅ Валидация входных данных
- ✅ Структура данных и опций
- ✅ Значения по умолчанию
- ✅ Множественные обновления опций

### Список тестов

#### Config Flow Tests (14 тестов)

1. **test_form_user_single_instance** - Проверка единственного экземпляра
2. **test_form_user_create_entry** - Создание config entry
3. **test_reconfigure_flow** - Перенастройка интеграции
4. **test_options_flow_init** - Инициализация options flow
5. **test_options_flow_update** - Обновление опций
6. **test_options_flow_default_values** - Значения по умолчанию
7. **test_validate_input** - Валидация входных данных
8. **test_config_flow_step_user_no_input** - Создание без ввода
9. **test_reconfigure_flow_with_no_changes** - Перенастройка без изменений
10. **test_options_flow_preserves_data** - Сохранение data при изменении options
11. **test_multiple_options_flow_updates** - Множественные обновления опций
12. **test_config_entry_data_structure** - Структура данных config entry
13. **test_config_entry_default_values** - Значения по умолчанию config entry
14. **test_options_flow_preserves_data** - Сохранение данных при options flow

## 🎯 Требования для Bronze уровня

Для достижения **Bronze** уровня по [Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/) требуется:

- ✅ **config-flow-test-coverage** - Full test coverage for the config flow

**Статус:** ✅ **ВЫПОЛНЕНО** - Config flow имеет полное покрытие тестами (14 тестов)

## 📝 Добавление новых тестов

### Шаблон теста

```python
async def test_new_feature(hass: HomeAssistant) -> None:
    """Test description."""
    # Arrange - подготовка
    # ...
    
    # Act - действие
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Assert - проверка
    assert result["type"] == FlowResultType.CREATE_ENTRY
```

### Использование фикстур

```python
async def test_with_mocks(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_device_manager: AsyncMock,
) -> None:
    """Test with fixtures."""
    # Тестовый код с использованием моков
    pass
```

## 🐛 Отладка тестов

### Запуск с отладочным выводом

```bash
# Показать print() вывод
pytest tests/ -s

# Показать логи
pytest tests/ --log-cli-level=DEBUG

# Остановиться на первой ошибке
pytest tests/ -x

# Повторить только упавшие тесты
pytest tests/ --lf
```

### Использование pdb

```python
async def test_debug(hass: HomeAssistant) -> None:
    """Test with debugger."""
    import pdb; pdb.set_trace()  # Точка останова
    # ...
```

## 📚 Полезные ссылки

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Home Assistant Testing](https://developers.home-assistant.io/docs/development_testing/)
- [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)

## ✅ Чеклист для добавления новых тестов

При добавлении новых тестов убедитесь:

- [ ] Тест имеет понятное описание (docstring)
- [ ] Тест использует правильные фикстуры
- [ ] Тест проверяет одну конкретную функциональность
- [ ] Тест использует async/await правильно
- [ ] Тест имеет четкую структуру Arrange-Act-Assert
- [ ] Тест покрывает как положительные, так и отрицательные сценарии
- [ ] Тест не зависит от других тестов
- [ ] Тест быстро выполняется (<1 секунды)
