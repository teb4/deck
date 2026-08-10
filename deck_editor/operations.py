"""Операции колоды: REPLACE, DELETE, INSERT, INSERT_HEAD."""

from typing import List, Tuple

from deck_editor.parser import Address, Operation
from deck_editor.config import max_deck_lines
from deck_editor.utils import AddressError, DeckLimitError, DeckSyntaxError


def validate_operations(operations: List[Operation], total_lines: int) -> None:
    """
    Валидирует все операции перед применением.
    Проверяет адреса, лимиты, конфликты.

    Операции в колоде выполняются последовательно и сдвигают номера строк
    (см. apply_operation / _apply_all), поэтому адрес каждой следующей
    операции валидируется относительно количества строк файла ПОСЛЕ
    применения всех предыдущих операций этой же колоды, а не относительно
    исходного размера файла.
    """
    # Считаем total payload lines
    total_payload = sum(len(op.payload) for op in operations)
    if total_payload > max_deck_lines:
        raise DeckLimitError(f"deck size limit exceeded: {total_payload} > {max_deck_lines}")

    # Валидируем каждую операцию относительно текущего (сдвинутого) размера файла
    current_lines = total_lines
    for op in operations:
        current_lines = _validate_single(op, current_lines)


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
            raise DeckSyntaxError("APPEND takes no address")
        return total_lines + len(op.payload)

    if op.address is None:
        raise DeckSyntaxError(f"{op.name} requires an address")

    # DELETE не должен иметь payload (fallback, если парсер не проверил)
    if op.name == "DELETE" and op.payload:
        raise DeckSyntaxError("unexpected payload after DELETE")

    start = op.address.start
    end = op.address.end

    # Валидация диапазона
    if end is not None and start > end:
        raise AddressError("invalid address range — start > end")

    # INSERT требует одиночный адрес
    if op.name == "INSERT" and end is not None:
        raise AddressError("INSERT requires single line address")

    # Валидация out of range (для INSERT адрес N — это существующая строка,
    # после которой вставляется payload, поэтому она тоже обязана существовать)
    if start < 1:
        raise AddressError(f"address out of file range (lines: 1-{total_lines})")
    if start > total_lines:
        raise AddressError(f"address out of file range (lines: 1-{total_lines})")

    # Для REPLACE/DELETE/REPLACE_REGEX с диапазоном
    if op.name in ("REPLACE", "DELETE", "REPLACE_REGEX") and end is not None:
        if end > total_lines:
            raise AddressError(f"address out of file range (lines: 1-{total_lines})")

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
        raise DeckSyntaxError(f"unknown operation: {op.name}")


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
    import re

    addr = op.address
    start_idx = addr.start - 1  # 0-индексация

    # Определяем end_idx
    if addr.is_to_end:
        end_idx = len(lines)
    elif addr.end is None:
        end_idx = addr.start
    else:
        end_idx = addr.end

    # Парсим sed-выражение: s/pattern/replacement/flags
    sed_expr = op.payload[0] if op.payload else ""
    pattern, replacement, flags = _parse_sed_expr(sed_expr)

    # compiled_re — None если выражение некорректно
    compiled_re = re.compile(pattern)
    has_global = "g" in flags

    # Строки до диапазона
    before = lines[:start_idx]
    # Строки после диапазона
    after = lines[end_idx:]

    # Применяем regex к строкам в диапазоне
    replaced_lines = []
    for i in range(start_idx, end_idx):
        line = lines[i]
        if has_global:
            new_line = compiled_re.sub(replacement, line)
        else:
            # Только первое совпадение
            new_line = compiled_re.sub(replacement, line, count=1)
        replaced_lines.append(new_line)

    return before + replaced_lines + after


def _parse_sed_expr(sed_expr: str) -> Tuple[str, str, str]:
    """Парсит sed-выражение s/pattern/replacement/flags.

    Возвращает (pattern, replacement, flags).
    Поддерживает разделители: /, |, #, ~
    """
    if len(sed_expr) < 2:
        raise DeckSyntaxError(f"invalid sed expression: {sed_expr}")

    # sed-выражение начинается с 's' за которым следует разделитель
    if not sed_expr.startswith("s"):
        raise DeckSyntaxError(f"invalid sed expression: must start with 's'")

    rest = sed_expr[1:]  # убираем 's'
    if not rest:
        raise DeckSyntaxError(f"invalid sed expression: empty after 's'")

    delimiter = rest[0]
    if delimiter not in ("/", "|", "#", "~"):
        raise DeckSyntaxError(f"invalid sed delimiter: {delimiter}")

    # Разделяем по разделителю
    parts = rest[1:].split(delimiter)
    if len(parts) < 3:
        raise DeckSyntaxError(f"invalid sed expression: need pattern, replacement, flags")

    pattern = parts[0]
    replacement = parts[1]
    flags = parts[2] if len(parts) > 2 else ""

    return pattern, replacement, flags


def _apply_append(lines: List[str], op: Operation) -> List[str]:
    """APPEND: добавляет payload в конец файла."""
    # Payload — добавляем \n к каждой строке
    payload = [line if line.endswith("\n") else line + "\n" for line in op.payload]
    return lines + payload
