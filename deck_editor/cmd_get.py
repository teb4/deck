"""Команда GET — чтение строк файла."""

import sys
from typing import Tuple

from deck_editor.parser import Address
from deck_editor.utils import AddressError, compute_xxhash, format_numbered
from deck_editor.logger import log_get


def cmd_get(file_path: str, addr_str: str) -> None:
    """
    Читает файл, извлекает диапазон строк по адресу,
    выводит REV и пронумерованные строки.
    """
    with open(file_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    rev = compute_xxhash(file_path)
    address = Address.parse(addr_str)

    # Валидация диапазона
    if address.end is not None and address.start > address.end:
        raise AddressError(
            "invalid address range — start > end",
            hint="for a range `N-M` the second number must be >= the first, e.g. `5-10`.")

    # Определяем конечную строку
    if address.end is None:
        end_idx = len(lines)
    else:
        end_idx = min(address.end, len(lines))

    # Пустой файл (0 байт) — возвращаем только REV
    if len(lines) == 0:
        print(f"REV: {rev}")
        return

    # Валидация out of range
    if address.start < 1:
        raise AddressError(
            f"address out of file range (lines: 1-{len(lines)})",
            hint=f"line {address.start} is outside the file, which has {len(lines)} line(s) (1-{len(lines)}).")
    if address.start > len(lines):
        raise AddressError(
            f"address out of file range (lines: 1-{len(lines)})",
            hint=f"line {address.start} is outside the file, which has {len(lines)} line(s) (1-{len(lines)}).")


    # Извлекаем строки (1-индексация)
    start_idx = address.start - 1
    selected = lines[start_idx:end_idx]

    # Форматируем вывод
    output_lines = [f"REV: {rev}"]
    output_lines.extend([format_numbered(start_idx + 1 + i, line) for i, line in enumerate(selected)])

    print("\n".join(output_lines))


def get_lines(file_path: str, addr_str: str) -> Tuple[str, str, int]:
    """
    Возвращает (rev, formatted_output, total_lines) программно.
    Используется внутри apply.py для DRY/APPLY.
    """
    with open(file_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    rev = compute_xxhash(file_path)
    address = Address.parse(addr_str)

    if address.end is not None and address.start > address.end:
        raise AddressError(
            "invalid address range — start > end",
            hint="for a range `N-M` the second number must be >= the first, e.g. `5-10`.")
    # Пустой файл (0 байт) — возвращаем только REV
    if len(lines) == 0:
        return rev, f"REV: {rev}", 0

    if address.start < 1:
        raise AddressError(
            f"address out of file range (lines: 1-{len(lines)})",
            hint=f"line {address.start} is outside the file, which has {len(lines)} line(s) (1-{len(lines)}).")
    if address.start > len(lines):
        raise AddressError(
            f"address out of file range (lines: 1-{len(lines)})",
            hint=f"line {address.start} is outside the file, which has {len(lines)} line(s) (1-{len(lines)}).")

    # Определяем конечную строку.
    # N- (is_to_end) — до конца файла; одиночный N (end is None, но НЕ is_to_end)
    # — ровно одна строка; N-M — до строки M. Раньше N и N- обрабатывались
    # одинаково (обе имели end is None) и читались «до конца», что ломало
    # семантику одиночной строки по документации
    # (README.md Addressing: `N` = Single line).
    if address.is_to_end:
        end_idx = len(lines)
    elif address.end is None:
        end_idx = address.start
    else:
        end_idx = min(address.end, len(lines))

    start_idx = address.start - 1
    selected = lines[start_idx:end_idx]

    # Логирование
    char_count = sum(len(line) for line in selected)
    log_get(file_path, addr_str, len(lines), char_count)

    output_lines = [f"REV: {rev}"]
    output_lines.extend([format_numbered(start_idx + 1 + i, line) for i, line in enumerate(selected)])

    return rev, "\n".join(output_lines), len(lines)


def get_rev_and_count(file_path: str) -> Tuple[str, int]:
    """
    Возвращает (rev, total_lines) без возврата списка строк.
    Используется вызовом rev() для быстрого обновления версии без
    загрузки содержимого файла в контекст.
    """
    with open(file_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    total_lines = len(lines)
    rev = compute_xxhash(file_path)

    return rev, total_lines


def _format_lines(lines: list, start: int) -> list:
    """Устаревшая обёртка — перенаправляет на format_numbered (для обратной совместимости)."""
    return [format_numbered(start + i, line) for i, line in enumerate(lines)]
