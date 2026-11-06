"""Применение колоды с семантикой «адреса относительно оригинала».

Адреса всех операций относятся к ОРИГИНАЛЬНОму файлу (тому, что прочитан через
GET). Вместо последовательного применения («цепочки»), когда каждая операция
работает с результатом предыдущей и номера строк сдвигаются, выполняется
слияние: нулевые вставки (INSERT/INSERT_HEAD/APPEND) ставятся в «дырки» между
строками, широкие операции (REPLACE/DELETE/REPLACE_REGEX) заменяют диапазоны.

Пересекающиеся области уже запрещены на этапе валидации (см.
`deck_editor.operations.check_overlaps` — он вызывает `_check_overlaps`),
поэтому здесь области гарантированно не конфликтуют.
"""

from typing import Dict, List, Tuple

from deck_editor.operations import _region, _regex_range_output
from deck_editor.parser import Operation


def apply_anchored(
    lines: List[str],
    operations: List[Operation],
    total_lines: int,
) -> List[str]:
    """
    Применяет операции относительно оригинального файла.

    Возвращает новый список строк. Широкие операции сортируются по началу и
    заменяют свои диапазоны; нулевые вставки группируются по «дырке» (порядок
    по колоде) и вставляются в нужные места.
    """
    width_ops: List[Tuple[int, int, List[str]]] = []
    zero_by_gap: Dict[int, List[str]] = {}
    for op in operations:
        output = _op_output(lines, op)
        region = _region(op, total_lines)
        if region[0] == "width":
            width_ops.append((region[1], region[2], output))
        else:
            zero_by_gap.setdefault(region[1], []).extend(output)
    width_ops.sort(key=lambda item: item[0])
    return _merge_anchored(lines, total_lines, width_ops, zero_by_gap)


def _op_output(lines: List[str], op: Operation) -> List[str]:
    """Возвращает строки, которые операция запишет на свою область."""
    if op.name == "DELETE":
        return []
    if op.name == "REPLACE_REGEX":
        addr = op.address
        start_idx = addr.start - 1
        if addr.is_to_end:
            end_idx = len(lines)
        elif addr.end is None:
            end_idx = addr.start
        else:
            end_idx = addr.end
        return _regex_range_output(lines, op, start_idx, end_idx)
    return _with_newlines(op.payload)


def _merge_anchored(
    lines: List[str],
    total_lines: int,
    width_ops: List[Tuple[int, int, List[str]]],
    zero_by_gap: Dict[int, List[str]],
) -> List[str]:
    """Сливает операции с оригинальным файлом в новый список строк."""
    result: List[str] = []
    width_index = 0
    num_width = len(width_ops)
    line = 1
    while line <= total_lines:
        # Нулевые вставки в «дырку» перед строкой `line` (после строки line-1).
        if line - 1 in zero_by_gap:
            result.extend(zero_by_gap[line - 1])
        # Широкая операция, начинающаяся на строке `line`.
        if width_index < num_width and width_ops[width_index][0] == line:
            _, end, output = width_ops[width_index]
            result.extend(output)
            line = end + 1
            width_index += 1
            continue
        result.append(lines[line - 1])
        line += 1
    # Нулевые вставки после последней строки (APPEND, INSERT total_lines).
    if total_lines in zero_by_gap:
        result.extend(zero_by_gap[total_lines])
    return result


def _with_newlines(payload: List[str]) -> List[str]:
    """Добавляет перевод строки к строкам payload, если его нет."""
    return [ln if ln.endswith("\n") else ln + "\n" for ln in payload]
