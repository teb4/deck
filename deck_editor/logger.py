"""Модуль логирования Deck Editor.

Логирование по умолчанию отключено.
Включается настройкой log_enabled в config.yaml.

Лог записывается в файл, имя задаётся в log_file в config.yaml.
Если log_file пустой — логи выводятся в stdout.
Лог всегда только добавляется (предыдущие данные никогда не стираются).

Формат лога:
    2026-08-10T14:32:11 GET file=<path> addr=<addr> lines=<n> chars=<n>
    2026-08-10T14:32:19 APPLY file=<path> rev=<rev>
    2026-08-10T14:32:19 REPLACE <start>-<end>
    2026-08-10T14:32:19 REPLACE_REGEX <start>-<end> s/foo/bar/g
    2026-08-10T14:32:19 APPEND <n>
    2026-08-10T14:32:19 END success
"""

import datetime
import os
import sys
import threading
from typing import Optional

from deck_editor.config import log_enabled, log_file

# Глобальное состояние
_logger_enabled: bool = log_enabled
_logger_lock = threading.Lock()
_log_fd = None  # Файловый дескриптор для append-режима


def _ensure_log_file():
    """Открывает файл лога в режиме append, если log_file задан."""
    global _log_fd
    if _log_fd is not None:
        return
    if not log_file:
        return
    # Создаём директорию, если не существует
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    _log_fd = open(log_file, "a", encoding="utf-8")


def is_enabled() -> bool:
    """Проверяет, включено ли логирование."""
    return _logger_enabled


def enable() -> None:
    """Включает логирование."""
    global _logger_enabled
    with _logger_lock:
        _logger_enabled = True


def disable() -> None:
    """Выключает логирование."""
    global _logger_enabled
    with _logger_lock:
        _logger_enabled = False


def _write_log(line: str) -> None:
    """Записывает строку лога в файл и/или stdout."""
    if not is_enabled():
        return
    with _logger_lock:
        # Выводим в stdout всегда
        print(line)
        # Если задан файл лога — дописываем
        if log_file:
            _ensure_log_file()
            if _log_fd is not None:
                _log_fd.write(line + "\n")
                _log_fd.flush()


def log_get(file_path: str, addr: str, total_lines: int, char_count: int) -> None:
    """Логгирует операцию GET."""
    if not is_enabled():
        return
    ts = _timestamp()
    _write_log(f"{ts} GET file={file_path} addr={addr} lines={total_lines} chars={char_count}")


def log_apply_start(file_path: str, rev: str) -> None:
    """Логгирует начало APPLY."""
    if not is_enabled():
        return
    ts = _timestamp()
    _write_log(f"{ts} APPLY file={file_path} rev={rev}")


def log_apply_end(success: bool) -> None:
    """Логгирует завершение APPLY."""
    if not is_enabled():
        return
    ts = _timestamp()
    status = "success" if success else "failure"
    _write_log(f"{ts} END {status}")


def log_replace(start: int, end: Optional[int]) -> None:
    """Логгирует операцию REPLACE."""
    if not is_enabled():
        return
    ts = _timestamp()
    addr = _format_addr(start, end)
    _write_log(f"{ts} REPLACE {addr}")


def log_replace_regex(start: int, end: Optional[int], sed_expr: str) -> None:
    """Логгирует операцию REPLACE_REGEX."""
    if not is_enabled():
        return
    ts = _timestamp()
    addr = _format_addr(start, end)
    _write_log(f"{ts} REPLACE_REGEX {addr} s/{sed_expr}")


def log_append(line_count: int) -> None:
    """Логгирует операцию APPEND."""
    if not is_enabled():
        return
    ts = _timestamp()
    _write_log(f"{ts} APPEND {line_count}")


def _timestamp() -> str:
    """Возвращает текущее время в формате ISO-8601 без микросекунд."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _format_addr(start: int, end: Optional[int]) -> str:
    """Форматирует адрес для логов."""
    if end is None:
        return str(start)
    return f"{start}-{end}"
