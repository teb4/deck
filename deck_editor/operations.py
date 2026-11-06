"""Операции колоды: REPLACE, DELETE, INSERT, INSERT_HEAD."""

import re
from typing import List, Tuple

from deck_editor.parser import Address, Operation
from deck_editor.config import max_deck_lines
from deck_editor.utils import AddressError, DeckLimitError, DeckSyntaxError


def validate_operations(operations: List[Operation], total_lines: int) -> None:
    """
    Валидирует все операции перед применением.
    Проверяет адреса, лимиты, конфликты.

    Адреса всех операций относятся к ОРИГИНАЛЬНОму файлу (тому, что прочитан
    через GET). Поэтому каждая операция валидируется относительно исходного
    размера файла `total_lines`, а не относительно размера «после предыдущих»
    операций. После валидации адресов проверяется, что области операций не
    пересекаются (см. _check_overlaps) — в одной колоде нельзя касаться
    одних и тех же строк оригинала.
    """
    # Считаем total payload lines
    total_payload = sum(len(op.payload) for op in operations)
    if total_payload > max_deck_lines:
        raise DeckLimitError(
            f"deck size limit exceeded: {total_payload} > {max_deck_lines}",
            hint=(f"the total payload exceeds the limit of {max_deck_lines} lines "
                  f"(found {total_payload}). Split the edit into smaller decks."),
        )

    # Валидируем каждой операции относительно ОРИГИНАЛЬНОго размера файла
    for op in operations:
        _validate_single(op, total_lines)

    # Области операций в оригинальном файле не должны пересекаться
    _check_overlaps(operations, total_lines)


def _validate_single(op: Operation, total_lines: int) -> int:
    """
    Валидирует одну операцию относительно текущего количества строк файла.
    Возвращает количество строк файла ПОСЛЕ применения этой операции —
    оно становится базой для валидации следующей операции в колоде.
    """
    if op.name == "INSERT_HEAD":
        return total_lines + len(op.payload)

    # APPEND не должен иметь address
    if op.name == "APPEND":
        if op.address is not None:
            raise DeckSyntaxError(
                "APPEND takes no address",
                hint="\"APPEND\" takes no address — write only \"APPEND\".",
            )
        return total_lines + len(op.payload)

    if op.address is None:
        raise DeckSyntaxError(
            f"{op.name} requires an address",
            hint=(f"\"{op.name}\" needs an address (N, N-M or N-), "
                  f"e.g. \"{op.name} 5\"."),
        )

    # DELETE не должен иметь payload (fallback, если парсер не проверил)
    if op.name == "DELETE" and op.payload:
        raise DeckSyntaxError(
            "unexpected payload after DELETE",
            hint="\"DELETE\" has no payload — delete by address only, e.g. \"DELETE 5\".",
        )

    start = op.address.start
    end = op.address.end

    # Валидация диапазона
    if end is not None and start > end:
        raise AddressError(
            "invalid address range — start > end",
            hint="for a range `N-M` the second number must be >= the first, e.g. `5-10`.",
        )

    # INSERT требует одиночный адрес
    if op.name == "INSERT" and end is not None:
        raise AddressError(
            "INSERT requires single line address",
            hint="\"INSERT\" takes only a single line N (e.g. `5`), not a range like `5-10`.",
        )

    # Валидация out of range (для INSERT адрес N — это существующая строка,
    # после которой вставляется payload, поэтому она тоже обязана существовать)
    if start < 1 or start > total_lines:
        raise AddressError(
            f"address out of file range (lines: 1-{total_lines})",
            hint=(f"line {start} is outside the file, which has {total_lines} line(s) "
                  f"(1-{total_lines}); use an address within that range."),
        )

    # Для REPLACE/DELETE/REPLACE_REGEX с диапазоном
    if op.name in ("REPLACE", "DELETE", "REPLACE_REGEX") and end is not None:
        if end > total_lines:
            raise AddressError(
                f"address out of file range (lines: 1-{total_lines})",
                hint=(f"the range ends at line {end}, but the file has only "
                      f"{total_lines} line(s) (1-{total_lines}); use a range within it."),
            )

    # Считаем, сколько строк займёт файл после этой операции
    if op.name == "REPLACE":
        removed = _range_length(op.address, total_lines)
        return total_lines - removed + len(op.payload)
    elif op.name == "DELETE":
        removed = _range_length(op.address, total_lines)
        return total_lines - removed
    elif op.name == "REPLACE_REGEX":
        removed = _range_length(op.address, total_lines)
        return total_lines - removed + len(op.payload)
    elif op.name == "APPEND":
        return total_lines + len(op.payload)
    elif op.name == "INSERT":
        return total_lines + len(op.payload)

    return total_lines


def _region(op: Operation, total_lines: int) -> Tuple[str, int, int]:
    """
    Возвращает области операции в ОРИГИНАЛЬНОм файле.

    ('width', start, end) — заменяемый/удаляемый диапазон строк (end включительно,
    1-индексация): для REPLACE, DELETE, REPLACE_REGEX.
    ('zero', gap) — «дырка» между строками, в которую вставляется текст:
    0 — перед строкой 1 (INSERT_HEAD), N — после строки N (INSERT),
    total_lines — после последней строки (APPEND).
    """
    if op.name in ("REPLACE", "DELETE", "REPLACE_REGEX"):
        start = op.address.start
        if op.address.is_to_end:
            end = total_lines
        elif op.address.end is None:
            end = start
        else:
            end = op.address.end
        return ("width", start, end)
    if op.name == "INSERT_HEAD":
        return ("zero", 0)
    if op.name == "INSERT":
        return ("zero", op.address.start)
    return ("zero", total_lines)  # APPEND


def _regions_conflict(a: Tuple[str, int, int], b: Tuple[str, int, int]) -> bool:
    """Взаимно исключают ли себя две области в оригинальном файле."""
    kind_a, kind_b = a[0], b[0]
    if kind_a == "width" and kind_b == "width":
        # Два диапазона пересекаются, если имеют общую строку.
        return max(a[1], b[1]) <= min(a[2], b[2])
    if kind_a == "zero" and kind_b == "zero":
        # Две вставка конфликтуют, если в разные «дырки».
        return a[1] != b[1]
    # Широкая область и вставка: конфликт, если «дырка» внутри или на границе.
    wide, narrow = (a, b) if kind_a == "width" else (b, a)
    return wide[1] <= narrow[1] <= wide[2]


def _check_overlaps(operations: List[Operation], total_lines: int) -> None:
    """
    Проверяет, что области операций в оригинальном файле не пересекаются.

    Ошибка «operations overlap», если две операции касаются одной области:
    два диапазона имеют общую строку; две вставка в разные «дырки»; вставка
    лежит внутри или на границе диапазона. Несколько вставок в ОДНУ «дырку»
    разрешены — порядок сохранения на этапе применения (см. apply_anchored).
    """
    regions = [_region(op, total_lines) for op in operations]
    for i in range(len(regions)):
        for j in range(i + 1, len(regions)):
            if _regions_conflict(regions[i], regions[j]):
                raise DeckSyntaxError(
                    "operations overlap",
                    hint=("two operations in the deck touch the same lines of the "
                          "original file. Put them in separate decks, or make "
                          "sure each operation targets a distinct part of the file."),
                )


def _range_length(addr: Address, total_lines: int) -> int:
    """Сколько строк покрывает адрес (для REPLACE/DELETE)."""
    if addr.is_to_end:
        return total_lines - addr.start + 1
    if addr.end is None:
        return 1
    return addr.end - addr.start + 1


def apply_operation(lines: List[str], op: Operation) -> List[str]:
    """
    Применяет одну операцию к списку строк.
    Возвращает новый список строк.
    """
    if op.name == "REPLACE":
        return _apply_replace(lines, op)
    elif op.name == "DELETE":
        return _apply_delete(lines, op)
    elif op.name == "INSERT":
        return _apply_insert(lines, op)
    elif op.name == "INSERT_HEAD":
        return _apply_insert_head(lines, op)
    elif op.name == "REPLACE_REGEX":
        return _apply_replace_regex(lines, op)
    elif op.name == "APPEND":
        return _apply_append(lines, op)
    else:
        raise DeckSyntaxError(
            f"unknown operation: {op.name}",
            hint="valid operations are REPLACE, DELETE, INSERT, INSERT_HEAD, REPLACE_REGEX, APPEND.",
        )


def _apply_replace(lines: List[str], op: Operation) -> List[str]:
    """REPLACE: заменяет диапазон строк на payload (M → N)."""
    addr = op.address
    start_idx = addr.start - 1  # 0-индексация

    # Определяем end_idx
    if addr.is_to_end:
        # N- → до конца файла
        end_idx = len(lines)
    elif addr.end is None:
        # N (single line) → одна строка
        end_idx = addr.start
    else:
        # N-M → диапазон
        end_idx = addr.end

    # Строки до замены
    before = lines[:start_idx]
    # Строки после замены
    after = lines[end_idx:]

    # Payload — добавляем \n к каждой строке
    payload = [line if line.endswith("\n") else line + "\n" for line in op.payload]

    return before + payload + after


def _apply_delete(lines: List[str], op: Operation) -> List[str]:
    """DELETE: удаляет диапазон строк."""
    addr = op.address
    start_idx = addr.start - 1  # 0-индексация

    if addr.is_to_end:
        end_idx = len(lines)
    elif addr.end is None:
        end_idx = addr.start
    else:
        end_idx = addr.end

    # Строки до удаления
    before = lines[:start_idx]
    # Строки после удаления
    after = lines[end_idx:]

    return before + after


def _apply_insert(lines: List[str], op: Operation) -> List[str]:
    """INSERT: вставляет payload после строки N."""
    addr = op.address
    insert_after = addr.start  # 1-индексация строки, после которой вставляем

    # Строки до вставки (включая строку N)
    before = lines[:insert_after]
    # Строки после вставки
    after = lines[insert_after:]

    # Payload — добавляем \n к каждой строке
    payload = [line if line.endswith("\n") else line + "\n" for line in op.payload]

    return before + payload + after


def _apply_insert_head(lines: List[str], op: Operation) -> List[str]:
    """INSERT_HEAD: вставляет payload перед строкой 1."""
    # Payload — добавляем \n к каждой строке
    payload = [line if line.endswith("\n") else line + "\n" for line in op.payload]
    return payload + lines


def _apply_replace_regex(lines: List[str], op: Operation) -> List[str]:
    """REPLACE_REGEX: применяет sed-выражение к строкам диапазона.

    Payload — одна строка sed-выражения вида s/pattern/replacement/flags.
    Применяется ко всем строкам в указанном диапазоне.
    """
    addr = op.address
    start_idx = addr.start - 1  # 0-индексация

    # Определяем end_idx
    if addr.is_to_end:
        end_idx = len(lines)
    elif addr.end is None:
        end_idx = addr.start
    else:
        end_idx = addr.end

    # Применяем regex к строкам в диапазоне
    replaced = _regex_range_output(lines, op, start_idx, end_idx)
    return lines[:start_idx] + replaced + lines[end_idx:]


def _regex_range_output(
    lines: List[str], op: Operation, start_idx: int, end_idx: int
) -> List[str]:
    """Возвращает строки диапазона [start_idx, end_idx) после sed-замены."""
    sed_expr = op.payload[0] if op.payload else ""
    pattern, replacement, flags = _parse_sed_expr(sed_expr)

    # compiled_re — None если выражение некорректно
    compiled_re = re.compile(pattern)
    has_global = "g" in flags

    replaced_lines = []
    for i in range(start_idx, end_idx):
        line = lines[i]
        if has_global:
            replaced_lines.append(compiled_re.sub(replacement, line))
        else:
            # Только первое совпадение
            replaced_lines.append(compiled_re.sub(replacement, line, count=1))
    return replaced_lines


def _parse_sed_expr(sed_expr: str) -> Tuple[str, str, str]:
    """Парсит sed-выражение s/pattern/replacement/flags.

    Возвращает (pattern, replacement, flags).
    Поддерживает разделители: /, |, #, ~
    """
    if len(sed_expr) < 2:
        raise DeckSyntaxError(
            f"invalid sed expression: {sed_expr}",
            hint="a sed expression must look like `s/pattern/replacement/flags`, e.g. `s/foo/bar/g`.",
        )

    # sed-выражение начинается с 's' за которым следует разделитель
    if not sed_expr.startswith("s"):
        raise DeckSyntaxError(
            f"invalid sed expression: must start with 's'",
            hint="a sed expression must start with `s` then a delimiter, e.g. `s/foo/bar/g`.",
        )

    rest = sed_expr[1:]  # убираем 's'
    if not rest:
        raise DeckSyntaxError(
            f"invalid sed expression: empty after 's'",
            hint="a sed expression must have content after `s`, e.g. `s/foo/bar/g`.",
        )

    delimiter = rest[0]
    if delimiter not in ("/", "|", "#", "~"):
        raise DeckSyntaxError(
            f"invalid sed delimiter: {delimiter}",
            hint="the sed delimiter must be one of `/`, `|`, `#`, `~`, e.g. `s/foo/bar/g`.",
        )

    # Разделяем по разделителю
    parts = rest[1:].split(delimiter)
    if len(parts) < 3:
        raise DeckSyntaxError(
            f"invalid sed expression: need pattern, replacement, flags",
            hint="a sed expression needs a pattern, a replacement and flags, "
                 "e.g. `s/foo/bar/g`.",
        )

    pattern = parts[0]
    replacement = parts[1]
    flags = parts[2] if len(parts) > 2 else ""

    return pattern, replacement, flags


def _apply_append(lines: List[str], op: Operation) -> List[str]:
    """APPEND: добавляет payload в конец файла."""
    # Payload — добавляем \n к каждой строке
    payload = [line if line.endswith("\n") else line + "\n" for line in op.payload]
    return lines + payload
