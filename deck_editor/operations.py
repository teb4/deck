"""Операции колоды: REPLACE, DELETE, INSERT, INSERT_HEAD."""

from typing import List, Tuple

from deck_editor.parser import Address, Operation
from deck_editor.config import max_deck_lines
from deck_editor.utils import AddressError, DeckLimitError, DeckSyntaxError


def validate_operations(operations: List[Operation], total_lines: int) -> None:
    """
    Валидирует все операции перед применением.
    Проверяет адреса, лимиты, конфликты.
    """
    # Считаем total payload lines
    total_payload = sum(len(op.payload) for op in operations)
    if total_payload > max_deck_lines:
        raise DeckLimitError(f"deck size limit exceeded: {total_payload} > {max_deck_lines}")

    # Валидируем каждую операцию
    for op in operations:
        _validate_single(op, total_lines)


def _validate_single(op: Operation, total_lines: int) -> None:
    """Валидирует одну операцию."""
    if op.name == "INSERT_HEAD":
        return  # Нет адреса

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

    # Валидация out of range
    if start < 1:
        raise AddressError(f"address out of file range (lines: 1-{total_lines})")
    if start > total_lines and op.name not in ("INSERT",):
        raise AddressError(f"address out of file range (lines: 1-{total_lines})")

    # Для REPLACE/DELETE с диапазоном
    if op.name in ("REPLACE", "DELETE") and end is not None:
        if end > total_lines:
            raise AddressError(f"address out of file range (lines: 1-{total_lines})")


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
