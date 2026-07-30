"""Загрузка конфигурации из YAML-файла."""

import pathlib

import yaml

_DEFAULTS = {
    "max_deck_lines": 5000,
    "max_create_lines": 50000,
    "diff_preview_lines": 10,
    "diff_preview_threshold": 50,
}


def _load_config() -> dict:
    """Загружает config.yaml из той же директории, где лежит этот модуль."""
    config_path = pathlib.Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _merged() -> dict:
    """Возвращает словарь с defaults, перекрытыми реальным YAML."""
    merged = dict(_DEFAULTS)
    merged.update(_load_config())
    return merged

# Публичные константы — читаются из конфига (с fallback на defaults)
max_deck_lines: int = int(_merged()["max_deck_lines"])
max_create_lines: int = int(_merged()["max_create_lines"])
diff_preview_lines: int = int(_merged()["diff_preview_lines"])
diff_preview_threshold: int = int(_merged()["diff_preview_threshold"])
