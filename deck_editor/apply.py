"""Применение колоды: DRY, DRY_ALL, APPLY."""

import os
import difflib
from typing import List, Optional, Tuple

from deck_editor.anchored import apply_anchored
from deck_editor.operations import apply_operation, validate_operations
from deck_editor.parser import Deck, Operation
from deck_editor.config import diff_preview_lines, diff_preview_threshold
from deck_editor.utils import (
    VersionConflictError,
    atomic_write,
    compute_content_hash,
    compute_xxhash,
    format_numbered,
)
from deck_editor.logger import (
    log_apply_start,
    log_apply_end,
    log_replace,
    log_replace_regex,
    log_append,
)


def apply(file_path: str, deck: Deck, workspace_root: str) -> Optional[str]:
    """
    Применяет колоду к файлу.
    Возвращает строку результата для DRY/DRY_ALL/APPLY, None если операция не определена.
    """

    # 1. Проверяем существование файла для APPLY
    if deck.mode == "APPLY" and not os.path.exists(file_path):
        from deck_editor.utils import DeckSyntaxError
        raise DeckSyntaxError(
            "file does not exist, use CREATE",
            hint="the target file does not exist. Use CREATE to create it first (or check the path).")

    # 1. Читаем файл и проверяем rev
    current_rev = compute_xxhash(file_path)

    if deck.rev is not None and deck.rev != current_rev:
        raise VersionConflictError(
            "version conflict — file changed",
            hint="the file changed since you read it. Call deck_get again to get a fresh REV, then retry.")

    # 2. Читаем строки
    with open(file_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    total_lines = len(lines)

    # 3. Валидируем операции
    validate_operations(deck.operations, total_lines)

    # 4. Логгируем начало APPLY
    log_apply_start(file_path, current_rev)

    # 5. Применяем операции относительно оригинального файла
    new_lines = _apply_all(lines, deck.operations, total_lines)

    # 6. Формируем новый rev
    new_content = "".join(new_lines)
    new_rev = compute_content_hash(new_content)

    if deck.mode == "DRY":
        # Diff-предпросмотр
        result = _format_diff(lines, new_lines, current_rev, new_rev, deck.operations)
        log_apply_end(True)
        return result

    elif deck.mode == "DRY_ALL":
        # Полный листинг
        result = _format_dry_all(new_lines, new_rev)
        log_apply_end(True)
        return result

    elif deck.mode == "APPLY":
        # Атомарная запись
        atomic_write(file_path, new_content)
        result = _format_apply(lines, new_lines, new_rev, deck.operations)
        log_apply_end(True)
        return result

    log_apply_end(False)
    return None


def _apply_all(
    lines: List[str], operations: List[Operation], total_lines: int
) -> List[str]:
    """Применяет все операции относительно оригинального файла.

    Адреса всех операций относятся к исходному файлу (тому, что прочитан через
    GET); перед применением они не сдвигаются — слияние делает
    `apply_anchored`. Это отличается от старой «цепочки», где каждая операция
    работала с результатом предыдущей и номера строк сдвигались.
    """
    for op in operations:
        _log_operation(op)
    return apply_anchored(lines, operations, total_lines)


def _log_operation(op: Operation) -> None:
    """Логгирует одну операцию."""
    if op.name == "REPLACE":
        addr = op.address
        start = addr.start
        end = addr.end if not addr.is_to_end else None
        log_replace(start, end)
    elif op.name == "REPLACE_REGEX":
        addr = op.address
        start = addr.start
        end = addr.end if not addr.is_to_end else None
        sed_expr = op.payload[0] if op.payload else ""
        log_replace_regex(start, end, sed_expr)
    elif op.name == "APPEND":
        log_append(len(op.payload))


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
    output_lines.extend([format_numbered(i + 1, line) for i, line in enumerate(lines)])
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
