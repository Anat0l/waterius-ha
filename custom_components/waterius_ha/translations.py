"""Утилиты для работы с переводами в интеграции Waterius."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Кэш для переводов: {(language, component, entity_key): translations_dict}
_TRANSLATIONS_CACHE: dict[tuple[str, str, str], dict[str, str]] = {}


async def load_translations_from_json(
    hass: HomeAssistant,
    language: str,
    component: str,
    entity_key: str,
) -> dict[str, str]:
    """Загрузка переводов из JSON файла с кэшированием.
    
    Args:
        hass: Экземпляр Home Assistant
        language: Язык для загрузки (например, 'ru', 'en')
        component: Компонент (например, 'select', 'sensor')
        entity_key: Ключ entity (например, 'channel_0_data_type_data')
        
    Returns:
        Словарь с переводами {internal_option: translated_option}
    """
    # Проверяем кэш
    cache_key = (language, component, entity_key)
    if cache_key in _TRANSLATIONS_CACHE:
        _LOGGER.debug(
            "Использованы кэшированные переводы для %s.%s.%s",
            language,
            component,
            entity_key,
        )
        return _TRANSLATIONS_CACHE[cache_key]
    
    translations_dict = {}
    
    try:
        # Определяем путь к файлу переводов
        translations_file = Path(__file__).parent / "translations" / f"{language}.json"
        
        # Если файл не найден, используем английский как fallback
        if not translations_file.exists():
            translations_file = Path(__file__).parent / "translations" / "en.json"
        
        if translations_file.exists():
            # Используем asyncio.to_thread для асинхронного чтения файла
            def _read_file() -> dict[str, Any]:
                with open(translations_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            
            translations_data = await asyncio.to_thread(_read_file)
            
            # Извлекаем переводы опций из структуры entity.{component}.{entity_key}.state
            select_translations = (
                translations_data.get("entity", {})
                .get(component, {})
                .get(entity_key, {})
                .get("state", {})
            )
            
            translations_dict = select_translations.copy()
            
            _LOGGER.debug(
                "Загружены переводы для %s.%s: %d опций",
                component,
                entity_key,
                len(translations_dict)
            )
        else:
            _LOGGER.warning("Файл переводов не найден: %s", translations_file)
    except Exception as e:
        _LOGGER.error(
            "Не удалось загрузить переводы для %s.%s: %s",
            component,
            entity_key,
            e
        )
        translations_dict.clear()
    
    # Сохраняем в кэш
    _TRANSLATIONS_CACHE[cache_key] = translations_dict
    
    return translations_dict


