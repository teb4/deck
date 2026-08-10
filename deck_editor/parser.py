"""Парсер колод Deck Editor.

Распознаёт заголовок, операции и терминатор согласно спецификации.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from deck_editor.utils import DeckSyntaxError


# Зарезервированные слова для операций
OPERATION_NAMES = {"REPLACE", "DELETE", "INSERT", "INSERT_HEAD",
                   "REPLACE_REGEX", "APPEND"}
HEADER_NAMES = {"DRY", "DRY_ALL", "APPLY"}
TERMINATOR_NAME = "END"

# Паттерн для адреса: N, N-M, N-
ADDR_PATTERN = re.compile(r"^(\d+)(?:-(\d+|-))?$")
ADDR_RANGE_PATTERN = re.compile(r"^(\d+)-(\d+)$")
ADDR_TO_END_PATTERN = re.compile(r"^(\d+)-$")


@dataclass
class Address:
    """Адрес в колоде: одиночная строка, диапазон или от строки до конца."""
    start: int
    end: Optional[int] = None  # None означает "до конца" (N-) или single (N)
    is_to_end: bool = False  # True для N-, False для N (single)

    @classmethod
    def parse(cls, addr_str: str) -> "Address":
        """Парсит строку адреса: '5', '5-10', '5-'."""
        # Сначала проверяем N- (range-to-end)
        m_to_end = ADDR_TO_END_PATTERN.match(addr_str)
        if m_to_end:
            return cls(start=int(m_to_end.group(1)), end=None, is_to_end=True)
        # Затем проверяем N-M (range)
        m_range = ADDR_RANGE_PATTERN.match(addr_str)
        if m_range:
            return cls(start=int(m_range.group(1)), end=int(m_range.group(2)), is_to_end=False)
        # Затем проверяем N (single line)
        m_single = re.match(r"^(\d+)$", addr_str)
        if m_single:
            return cls(start=int(m_single.group(1)), end=None, is_to_end=False)
        raise DeckSyntaxError(f"invalid address: {addr_str}")

    def __str__(self) -> str:
        if self.is_to_end:
            # range-to-end: N-
            return f"{self.start}-"
        if self.end is None:
            # single line: N
            return str(self.start)
        # range: N-M
        return f"{self.start}-{self.end}"

    def __repr__(self) -> str:
        return f"Address({self})"

    def to_tuple(self) -> Tuple[int, int]:
        """Возвращает (start, end) для валидации."""
        return (self.start, self.end)


@dataclass
class Operation:
    """Операция в колоде."""
    name: str  # REPLACE, DELETE, INSERT, INSERT_HEAD
    address: Optional[Address] = None
    skip: bool = False
    payload: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        addr = f" {self.address}" if self.address else ""
        skip = " SKIP" if self.skip else ""
        return f"Op({self.name}{addr}{skip}, payload={len(self.payload)} lines)"


@dataclass
class Deck:
    """Колода Deck Editor."""
    mode: str  # DRY, DRY_ALL, APPLY
    rev: Optional[str] = None
    operations: List[Operation] = field(default_factory=list)
    marker: str = "@"

    def __repr__(self) -> str:
        return f"Deck({self.mode}, rev={self.rev}, ops={len(self.operations)})"


def parse_deck(text: str) -> Deck:
    """
    Парсит текст колоды.

    Grammar:
        колода       := заголовок тело терминатор
        заголовок    := маркер ("DRY" | "DRY_ALL" | "APPLY") [rev]
        маркер       := "@" | "$"
        тело         := operation+
        operation    := маркер op_name [addr] [SKIP] [payload]
        op_name      := "REPLACE" | "DELETE" | "INSERT" | "INSERT_HEAD"
        терминатор   := маркер "END"

    Важно: терминатор — это всегда последняя строка колоды.
    """
    lines = text.splitlines()
    if not lines:
        raise DeckSyntaxError("deck must start with DRY, DRY_ALL or APPLY")

    # 0. Проверяем терминатор — он всегда последняя строка колоды
    last_line = lines[-1].strip()
    if not _is_terminator(last_line, None):
        raise DeckSyntaxError("deck not terminated by END")

    # Определяем маркер из терминатора
    term_marker, term_cmd = _parse_terminator(last_line, None)
    if term_cmd != TERMINATOR_NAME:
        raise DeckSyntaxError("deck not terminated by END")

    # 1. Парсим заголовок
    header_line = lines[0].strip()
    deck, header_end = _parse_header(header_line)
    marker = deck.marker

    if header_end >= len(lines):
        raise DeckSyntaxError("deck must start with DRY, DRY_ALL or APPLY")

    # 2. Проверяем, что терминатор совпадает с маркером заголовка
    if term_marker != marker:
        raise DeckSyntaxError("terminator does not match deck marker")

    # 3. Парсим тело — операции (до предпоследней строки, т.к. последняя — терминатор)
    ops, body_end = _parse_operations(lines, header_end, marker)
    deck.operations = ops

    # 4. Проверяем, что body_end указывает на терминатор (предпоследняя строка)
    if body_end != len(lines) - 1:
        raise DeckSyntaxError("trailing lines after END")

    # 5. Валидация операций
    _validate_parsed_operations(deck.operations)

    return deck


def _validate_parsed_operations(operations: List[Operation]) -> None:
    """Валидация операций на этапе парсинга (приоритеты 6–11 из spec §15).

    Проверка DELETE with payload (приоритет 5) выполняется в _parse_operation
    на этапе Fast-Fail — сразу при обнаружении первой строки payload.
    """
    for op in operations:
        # INSERT требует одиночный адрес (приоритет 8)
        if op.name == "INSERT" and op.address is not None and op.address.end is not None:
            raise DeckSyntaxError("INSERT requires single line address")

        # INSERT_HEAD не должен иметь address (приоритет 9)
        if op.name == "INSERT_HEAD" and op.address is not None:
            raise DeckSyntaxError("INSERT_HEAD takes no address")

        # REPLACE_REGEX требует адрес (N, N-M, N-)
        if op.name == "REPLACE_REGEX" and op.address is None:
            raise DeckSyntaxError("REPLACE_REGEX requires an address")

        # APPEND не должен иметь address
        if op.name == "APPEND" and op.address is not None:
            raise DeckSyntaxError("APPEND takes no address")

        # APPEND не должен иметь SKIP
        if op.name == "APPEND" and op.skip:
            raise DeckSyntaxError("APPEND does not support SKIP")

        # REPLACE_REGEX не должен иметь SKIP (payload всегда идёт до END)
        if op.name == "REPLACE_REGEX" and op.skip:
            raise DeckSyntaxError("REPLACE_REGEX does not support SKIP")

        # Валидация диапазона: N-M где M < N (приоритет 11)
        if op.address is not None and op.address.end is not None:
            if op.address.start > op.address.end:
                raise DeckSyntaxError("invalid address range — start > end")


def _parse_header(line: str) -> Tuple[Deck, int]:
    """
    Парсит заголовок колоды.
    Возвращает Deck и индекс следующей строки после заголовка.
    """
    if not line:
        raise DeckSyntaxError("deck must start with DRY, DRY_ALL or APPLY")

    # Определяем маркер
    if line.startswith("@"):
        marker = "@"
        rest = line[1:]
    elif line.startswith("$"):
        marker = "$"
        rest = line[1:]
    else:
        raise DeckSyntaxError("deck must start with DRY, DRY_ALL or APPLY")

    # Парсим команду
    parts = rest.split()
    if not parts:
        raise DeckSyntaxError("deck must start with DRY, DRY_ALL or APPLY")

    cmd = parts[0]
    if cmd not in HEADER_NAMES:
        raise DeckSyntaxError("deck must start with DRY, DRY_ALL or APPLY")

    rev = parts[1] if len(parts) > 1 else None
    if rev is None:
        raise DeckSyntaxError('<rev> is mandatory for existing files')
    if len(rev) != 16 or not all(c in '0123456789abcdef' for c in rev):
        raise DeckSyntaxError('invalid <rev> format')
    return Deck(mode=cmd, rev=rev, marker=marker), 1


def _parse_operations(
    lines: List[str],
    start: int,
    marker: str,
) -> Tuple[List[Operation], int]:
    """
    Парсит операции до предпоследней строки (терминатор — всегда последняя).
    Возвращает список операций и индекс терминатора.
    """
    operations: List[Operation] = []
    idx = start
    has_skip = False

    while idx < len(lines) - 1:
        raw_line = lines[idx]
        line = raw_line.strip() if idx < len(lines) else ""

        # Проверяем, начинается ли строка с маркера
        if raw_line and raw_line[0] == marker:
            # Это новая команда
            if has_skip:
                raise DeckSyntaxError("operation after SKIP")
            # Проверяем, не терминатор ли это (ранний END)
            if _is_terminator(line, marker):
                return operations, idx
            op, next_idx = _parse_operation(lines, idx, marker)
            operations.append(op)
            if op.skip:
                has_skip = True
                # SKIP — последняя операция, payload уже собран
                # next_idx указывает на терминатор
                return operations, next_idx
            idx = next_idx
        elif has_skip:
            # После SKIP — payload идёт до терминатора, пропускаем
            idx += 1
        else:
            # Это не команда и не начинается с маркера — ошибка
            raise DeckSyntaxError("unexpected line — expected command or payload")



    # idx указывает на терминатор — это нормально
    return operations, idx


def _parse_operation(
    lines: List[str],
    start: int,
    marker: str,
) -> Tuple[Operation, int]:
    """
    Парсит одну операцию.
    Возвращает Operation и индекс следующей строки после payload.
    """
    line = lines[start].strip()
    # Убираем маркер
    rest = line[1:]
    parts = rest.split()

    if not parts:
        raise DeckSyntaxError("deck must start with DRY, DRY_ALL or APPLY")

    op_name = parts[0]

    # Fast-Fail: проверяем, что команда известна
    if op_name not in OPERATION_NAMES:
        raise DeckSyntaxError(f"unknown operation: {op_name}")

    address = None
    skip = False
    payload_start = start + 1
    if len(parts) > 1:


        second = parts[1]
        if second == "SKIP":
            if len(parts) > 2:
                raise DeckSyntaxError("SKIP takes no arguments")
            skip = True
            payload_start = start + 1
        elif op_name == "INSERT_HEAD":
            raise DeckSyntaxError("INSERT_HEAD takes no address")
        else:
            # Это адрес
            address = Address.parse(second)
            # Проверяем, есть ли SKIP после адреса
            if len(parts) > 2 and parts[2] == "SKIP":
                if len(parts) > 3:
                    raise DeckSyntaxError("SKIP takes no arguments")
                skip = True
                payload_start = start + 1
            else:
                payload_start = start + 1


    # Fast-Fail: DELETE не должен иметь SKIP (spec §6, §11) — проверяем ДО payload
    if op_name == "DELETE" and skip:
        raise DeckSyntaxError("DELETE does not support SKIP")

    # Fast-Fail: REPLACE_REGEX не должен иметь SKIP (payload всегда идёт до END)
    if op_name == "REPLACE_REGEX" and skip:
        raise DeckSyntaxError("REPLACE_REGEX does not support SKIP")

    # Fast-Fail: DELETE не должен иметь payload (spec §15, приоритет 5)
    if op_name == "DELETE" and len(parts) > 2:
        raise DeckSyntaxError("unexpected payload after DELETE")

    op = Operation(name=op_name, address=address, skip=skip)


    # Если SKIP — payload идёт до терминатора
    if skip:
        idx = payload_start
        while idx < len(lines):
            if _is_terminator(lines[idx].strip(), marker):
                # idx указывает на терминатор — возвращаем его
                return op, idx
            op.payload.append(lines[idx])
            idx += 1
        # Если дошли до конца без терминатора — вернём len(lines)
        return op, idx

    # REPLACE_REGEX — payload (sed-выражение) до терминатора
    if op_name == "REPLACE_REGEX":
        idx = payload_start
        while idx < len(lines) - 1:
            next_line = lines[idx].strip()
            if _is_command(next_line, marker) or _is_terminator(next_line, marker):
                return op, idx
            op.payload.append(lines[idx])
            idx += 1
        return op, idx

    # APPEND — payload (строки для добавления) до терминатора
    if op_name == "APPEND":
        idx = payload_start
        while idx < len(lines) - 1:
            next_line = lines[idx].strip()
            if _is_command(next_line, marker) or _is_terminator(next_line, marker):
                return op, idx
            op.payload.append(lines[idx])
            idx += 1
        return op, idx

    # Для INSERT/INSERT_HEAD — payload до следующей команды, терминатора или конца тела
    if op_name in ("INSERT", "INSERT_HEAD"):
        idx = payload_start
        while idx < len(lines) - 1:
            next_line = lines[idx].strip()
            if _is_command(next_line, marker) or _is_terminator(next_line, marker):
                # idx указывает на следующую команду или терминатор — вернём его
                return op, idx
            op.payload.append(lines[idx])
            idx += 1
        # idx указывает на терминатор или конец — вернём idx
        return op, idx

    # Для REPLACE — payload до следующей команды, терминатора или конца тела
    if op_name == "REPLACE":
        idx = payload_start
        while idx < len(lines) - 1:
            next_line = lines[idx].strip()
            if _is_command(next_line, marker) or _is_terminator(next_line, marker):
                # idx указывает на следующую команду или терминатор — вернём его
                return op, idx
            op.payload.append(lines[idx])
            idx += 1
        # idx указывает на терминатор или конец — вернём idx
        return op, idx

    # DELETE — Fast-Fail: если есть хоть одна строка payload, бросаем ошибку сразу
    if op_name == "DELETE":
        idx = payload_start
        while idx < len(lines) - 1:
            next_line = lines[idx].strip()
            if _is_command(next_line, marker) or _is_terminator(next_line, marker):
                return op, idx
            # Первая строка payload — ошибка, бросаем немедленно
            raise DeckSyntaxError("unexpected payload after DELETE")
        return op, idx

    return op, payload_start


def _is_command(line: str, marker: str) -> bool:
    """Проверяет, является ли строка командной (начинается с маркера + op_name)."""
    if not line or line[0] != marker:
        return False
    rest = line[1:].strip()
    for op_name in OPERATION_NAMES:
        if rest.startswith(op_name):
            after = rest[len(op_name):]
            if after == "" or after[0] == " ":
                return True
    return False


def _is_terminator(line: str, marker: Optional[str]) -> bool:
    """Проверяет, является ли строка терминатором."""
    if not line:
        return False
    # Если marker не указан — проверяем любой маркер
    if marker is None:
        if line[0] not in ('@', '$'):
            return False
        rest = line[1:].strip()
        return rest == TERMINATOR_NAME
    # Если marker указан — проверяем конкретный
    if line[0] != marker:
        return False
    rest = line[1:].strip()
    return rest == TERMINATOR_NAME


def _parse_terminator(line: str, expected_marker: Optional[str]) -> Tuple[str, str]:
    """Парсит терминатор, возвращает (marker, command)."""
    if not line:
        raise DeckSyntaxError("deck not terminated by END")
    marker = line[0]
    rest = line[1:].strip()
    return marker, rest
