"""Команда GET — чтение строк файла."""

import sys
from typing import Tuple

from deck_editor.parser import Address
from deck_editor.utils import AddressError, compute_xxhash


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
        raise AddressError(f"invalid address range — start > end")

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
        raise AddressError(f"address out of file range (lines: 1-{len(lines)})")
    if address.start > len(lines):
        raise AddressError(f"address out of file range (lines: 1-{len(lines)})")


    # Извлекаем строки (1-индексация)
    start_idx = address.start - 1
    selected = lines[start_idx:end_idx]

    # Форматируем вывод
    output_lines = [f"REV: {rev}"]
    output_lines.extend(_format_lines(selected, address.start))

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
        raise AddressError("invalid address range — start > end")
    # Пустой файл (0 байт) — возвращаем только REV
    if len(lines) == 0:
        return rev, f"REV: {rev}", 0

    if address.start < 1:
        raise AddressError(f"address out of file range (lines: 1-{len(lines)})")
    if address.start > len(lines):
        raise AddressError(f"address out of file range (lines: 1-{len(lines)})")

    # Определяем конечную строку
    if address.end is None:
        end_idx = len(lines)
    else:
        end_idx = min(address.end, len(lines))

    start_idx = address.start - 1
    selected = lines[start_idx:end_idx]


    output_lines = [f"REV: {rev}"]
    output_lines.extend(_format_lines(selected, address.start))


    return rev, "\n".join(output_lines), len(lines)


def _format_lines(lines: list, start: int) -> list:
    """Форматирует строки в формат REV-вывода (NNNNNN:text / NNNNNNe)."""
    result = []
    for i, line in enumerate(lines):
        line_num = start + i
        padded = f"{line_num:06d}"
        content = line.rstrip("\n").rstrip("\r\n")
        if content == "":
            result.append(f"{padded}e")
        else:
            result.append(f"{padded}:{content}")
    return result
