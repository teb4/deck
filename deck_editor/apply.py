"""Применение колоды: DRY, DRY_ALL, APPLY."""

import os
import difflib
from typing import List, Optional, Tuple

from deck_editor.operations import apply_operation, validate_operations
from deck_editor.parser import Deck, Operation
from deck_editor.config import diff_preview_lines, diff_preview_threshold
from deck_editor.utils import (
    VersionConflictError,
    atomic_write,
    compute_content_hash,
    compute_xxhash,
)


def apply(file_path: str, deck: Deck, workspace_root: str) -> Optional[str]:
    """
    Применяет колоду к файлу.
    Возвращает строку результата для DRY/DRY_ALL/APPLY, None если операция не определена.
    """

    # 1. Проверяем существование файла для APPLY
    if deck.mode == "APPLY" and not os.path.exists(file_path):
        from deck_editor.utils import DeckSyntaxError
        raise DeckSyntaxError("file does not exist, use CREATE")

    # 1. Читаем файл и проверяем rev
    current_rev = compute_xxhash(file_path)

    if deck.rev is not None and deck.rev != current_rev:
        raise VersionConflictError("version conflict — file changed")

    # 2. Читаем строки
    with open(file_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    total_lines = len(lines)

    # 3. Валидируем операции
    validate_operations(deck.operations, total_lines)

    # 4. Применяем операции
    new_lines = _apply_all(lines, deck.operations)

    # 5. Формируем новый rev
    new_content = "".join(new_lines)
    new_rev = compute_content_hash(new_content)

    if deck.mode == "DRY":
        # Diff-предпросмотр
        result = _format_diff(lines, new_lines, current_rev, new_rev, deck.operations)
        return result

    elif deck.mode == "DRY_ALL":
        # Полный листинг
        result = _format_dry_all(new_lines, new_rev)
        return result

    elif deck.mode == "APPLY":
        # Атомарная запись
        atomic_write(file_path, new_content)
        result = _format_apply(lines, new_lines, new_rev, deck.operations)
        return result

    return None


def _apply_all(lines: List[str], operations: List[Operation]) -> List[str]:
    """Последовательно применяет все операции."""
    result = list(lines)
    for op in operations:
        result = apply_operation(result, op)
    return result


def _format_diff(
    old_lines: List[str],
    new_lines: List[str],
    old_rev: str,
    new_rev: str,
    operations: List[Operation],
) -> str:
    """Форматирует diff-предпросмотр."""
    result = []
    result.append(f"REV: {new_rev} (would be new)")
    result.append(f"Original: {old_rev} → Modified: {new_rev}")

    # Формируем unified diff
    old_text = "".join(old_lines)
    new_text = "".join(new_lines)

    old_list = old_lines if old_lines else [""]
    new_list = new_lines if new_lines else [""]

    diff = difflib.unified_diff(
        old_list,
        new_list,
        lineterm="",
        fromfile="original",
        tofile="modified",
    )

    diff_lines = list(diff)
    # Показываем первые N и последние N строк diff
    if len(diff_lines) > diff_preview_threshold:
        preview = diff_lines[:diff_preview_lines]
        preview.append("... скрыто ...\n")
        preview.extend(diff_lines[-diff_preview_lines:])
        diff_lines = preview

    for dl in diff_lines:
        result.append(dl.rstrip("\n"))

    # Сводка операций
    result.append("")
    result.append("Operations applied:")
    for op in operations:
        addr = str(op.address) if op.address else "HEAD"
        if op.name == "REPLACE":
            if op.address.is_to_end:
                count = len(old_lines) - op.address.start + 1
            elif op.address.end is None:
                count = 1
            else:
                count = op.address.end - op.address.start + 1
            result.append(
                f"- REPLACE lines {addr} ({count} lines replaced with {len(op.payload)} lines)"
            )
        elif op.name == "DELETE":
            if op.address.is_to_end:
                count = len(old_lines) - op.address.start + 1
            elif op.address.end is None:
                count = 1
            else:
                count = op.address.end - op.address.start + 1
            result.append(f"- DELETE lines {addr} ({count} lines deleted)")
        elif op.name == "INSERT":
            result.append(
                f"- INSERT after line {op.address.start} ({len(op.payload)} lines inserted)"
            )
        elif op.name == "INSERT_HEAD":
            result.append(f"- INSERT_HEAD ({len(op.payload)} lines inserted)")
        elif op.name == "REPLACE_REGEX":
            if op.address.is_to_end:
                count = len(old_lines) - op.address.start + 1
            elif op.address.end is None:
                count = 1
            else:
                count = op.address.end - op.address.start + 1
            result.append(
                f"- REPLACE_REGEX lines {addr} ({count} lines regex-replaced)"
            )
        elif op.name == "APPEND":
            result.append(
                f"- APPEND ({len(op.payload)} lines appended)"
            )
    return "\n".join(result)


def _format_dry_all(lines: List[str], rev: str) -> str:
    """Форматирует полный нумерованный листинг."""
    # Пустой файл (0 байт)
    if not lines:
        return f"REV: {rev} (would be new)\n(Empty file: 0 lines)"
    output_lines = [f"REV: {rev}"]
    for i, line in enumerate(lines):
        line_num = i + 1
        padded = f"{line_num:06d}"
        content = line.rstrip("\n").rstrip("\r\n")
        if content == "":
            output_lines.append(f"{padded}e")
        else:
            output_lines.append(f"{padded}:{content}")
    return "\n".join(output_lines)



def _format_apply(old_lines: List[str], new_lines: List[str], rev: str, operations: List[Operation]) -> str:
    """Форматирует результат APPLY."""
    result = []
    result.append("APPLIED successfully")
    result.append(f"REV: {rev} (new)")
    result.append("Operations applied:")

    for op in operations:
        if op.name == "REPLACE":
            addr = str(op.address)
            if op.address.is_to_end:
                count = len(old_lines) - op.address.start + 1
            elif op.address.end is None:
                count = 1
            else:
                count = op.address.end - op.address.start + 1
            result.append(
                f"- REPLACE lines {addr} ({count} lines replaced with {len(op.payload)} lines)"
            )
        elif op.name == "DELETE":
            addr = str(op.address)
            if op.address.is_to_end:
                count = len(old_lines) - op.address.start + 1
            elif op.address.end is None:
                count = 1
            else:
                count = op.address.end - op.address.start + 1
            result.append(f"- DELETE lines {addr} ({count} lines deleted)")
        elif op.name == "INSERT":
            result.append(
                f"- INSERT after line {op.address.start} ({len(op.payload)} lines inserted)"
            )
        elif op.name == "INSERT_HEAD":
            result.append(f"- INSERT_HEAD ({len(op.payload)} lines inserted)")
        elif op.name == "REPLACE_REGEX":
            addr = str(op.address)
            if op.address.is_to_end:
                count = len(old_lines) - op.address.start + 1
            elif op.address.end is None:
                count = 1
            else:
                count = op.address.end - op.address.start + 1
            result.append(
                f"- REPLACE_REGEX lines {addr} ({count} lines regex-replaced)"
            )
        elif op.name == "APPEND":
            result.append(
                f"- APPEND ({len(op.payload)} lines appended)"
            )

    return "\n".join(result)
