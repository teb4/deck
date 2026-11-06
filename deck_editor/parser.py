"""Парсер колод Deck Editor.

Распознаёт заголовок, операции и терминатор согласно спецификации.
Все синтаксические ошибки несут подсказку (hint) о том, как должно быть
правильно — для агентов LLM.
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

# Операции, которым нужен адрес
_ADDRESSED_OPS = {"REPLACE", "DELETE", "INSERT", "REPLACE_REGEX"}
# Операции, которым адрес (и SKIP) не нужен
_ADDRESSLESS_OPS = {"INSERT_HEAD", "APPEND"}

# Паттерн для адреса: N, N-M, N-
ADDR_PATTERN = re.compile(r"^(\d+)(?:-(\d+|-))?$")
ADDR_RANGE_PATTERN = re.compile(r"^(\d+)-(\d+)$")
ADDR_TO_END_PATTERN = re.compile(r"^(\d+)-$")


@dataclass
class Address:
    """Адрес в колоде: одиночная строка, диапазон или от строки до конца."""
    start: int
    end: Optional[int] = None  # None означает "до конца" (N-) or single (N)
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
        raise DeckSyntaxError(
            f"invalid address: {addr_str}",
            hint="address must be `N`, `N-M` or `N-` with digits only, e.g. `5`, `5-10` or `5-`",
        )

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


def _marker_from_line(line: str) -> Optional[str]:
    """Определяет маркер из строки: '@', '$' или None, если строка не с маркера."""
    if line and line[0] in ("@", "$"):
        return line[0]
    return None


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

    Важно: маркер определяется по первой строке. Если он не определён — это
    ошибка, и проверку терминатора можно не делать (заголовок приоритетнее).
    """
    lines = text.splitlines()
    if not lines:
        raise DeckSyntaxError(
            "deck must start with DRY, DRY_ALL or APPLY",
            hint="the deck is empty — start it with a header line, e.g. \"@APPLY a1b2c3d4e5f6\"",
        )

    header_line = lines[0].strip()

    # 0. Маркер определяется по первой строке. Если маркер не определён —
    #    это ошибка, и проверку терминатора можно не делать.
    marker = _marker_from_line(header_line)
    if marker is None:
        raise DeckSyntaxError(
            "deck must start with DRY, DRY_ALL or APPLY",
            hint=("first line must start with a marker (`@` or `$`), then a command, "
                  "e.g. \"@APPLY a1b2c3d4e5f6\""),
        )

    # 1. Заголовок
    deck, header_end = _parse_header(header_line, marker)

    if header_end >= len(lines):
        raise DeckSyntaxError(
            "deck must start with DRY, DRY_ALL or APPLY",
            hint=(f"first line must be a header \"{marker}APPLY <rev>\" where "
                  "<rev> is 16 hex chars (0-9a-f)"),
        )

    # 2. Терминатор — проверяем уже известным маркером. Различаем «терминатора
    #    нет вообще» и «терминатор с неправильным маркером».
    last_line = lines[-1].strip()
    if _is_terminator(last_line, None):
        term_marker, _ = _parse_terminator(last_line, None)
        if term_marker != marker:
            raise DeckSyntaxError(
                "terminator does not match deck marker",
                hint=(f"header and terminator must share the marker. Header uses "
                      f"\"{marker}\", so the last line must be \"{marker}END\""),
            )
    else:
        raise DeckSyntaxError(
            "deck not terminated by END",
            hint=f"the last line must read \"{marker}END\" (e.g. \"{marker}END\")",
        )

    # 3. Тело — операции
    deck.marker = marker
    ops, body_end = _parse_operations(lines, header_end, marker)
    deck.operations = ops

    # 4. Проверяем, что body_end указывает на терминатор (предпоследняя строка)
    if body_end != len(lines) - 1:
        raise DeckSyntaxError(
            "trailing lines after END",
            hint=f"nothing may appear after \"{marker}END\" — it must be the last line",
        )

    # 5. Валидация операций
    _validate_parsed_operations(deck.operations, marker)

    return deck


def _validate_parsed_operations(operations: List[Operation], marker: str = "@") -> None:
    """Валидация операций на этапе парсинга (приоритеты 6–11 из spec §15).

    Проверка DELETE with payload (приоритет 5) выполняется в _parse_operation
    на этапе Fast-Fail — сразу при обнаружении первой строки payload.
    """
    for op in operations:
        # INSERT требует одиночный адрес (приоритет 8)
        if op.name == "INSERT" and op.address is not None and op.address.end is not None:
            raise DeckSyntaxError(
                "INSERT requires single line address",
                hint=(f"\"{marker}INSERT\" takes only a single line, e.g. "
                      f"\"{marker}INSERT 5\", not a range"),
            )

        # INSERT_HEAD не должен иметь address
        if op.name == "INSERT_HEAD" and op.address is not None:
            raise DeckSyntaxError(
                "INSERT_HEAD takes no address",
                hint=f"\"{marker}INSERT_HEAD\" takes no address — write only \"{marker}INSERT_HEAD\".",
            )

        # REPLACE_REGEX требует адрес (N, N-M, N-)
        if op.name == "REPLACE_REGEX" and op.address is None:
            raise DeckSyntaxError(
                "REPLACE_REGEX requires an address",
                hint=f"\"{marker}REPLACE_REGEX\" needs an address, e.g. \"{marker}REPLACE_REGEX 1-10\".",
            )

        # APPEND не должен иметь address
        if op.name == "APPEND" and op.address is not None:
            raise DeckSyntaxError(
                "APPEND takes no address",
                hint=f"\"{marker}APPEND\" takes no address — write only \"{marker}APPEND\".",
            )

        # APPEND не должен иметь SKIP
        if op.name == "APPEND" and op.skip:
            raise DeckSyntaxError(
                "APPEND does not support SKIP",
                hint=f"\"{marker}APPEND\" takes no address and no SKIP — write only \"{marker}APPEND\".",
            )

        # REPLACE_REGEX не должен иметь SKIP (payload всегда идёт до END)
        if op.name == "REPLACE_REGEX" and op.skip:
            raise DeckSyntaxError(
                "REPLACE_REGEX does not support SKIP",
                hint=(f"\"{marker}REPLACE_REGEX\" payload runs to "
                      f"\"{marker}END\" and takes no SKIP"),
            )

        # Валидация диапазона: N-M где M < N (приоритет 11)
        if op.address is not None and op.address.end is not None:
            if op.address.start > op.address.end:
                raise DeckSyntaxError(
                    "invalid address range — start > end",
                    hint="for a range `N-M` the second number must be >= the first, e.g. `5-10`",
                )


def _parse_header(line: str, marker: Optional[str] = None) -> Tuple[Deck, int]:
    """
    Парсит заголовок колоды.
    Возвращает Deck и индекс следующей строки после заголовка.
    """
    if marker is None:
        marker = _marker_from_line(line) or "@"
    if not line or line[0] != marker:
        raise DeckSyntaxError(
            "deck must start with DRY, DRY_ALL or APPLY",
            hint=(f"first line must start with the marker \"{marker}\" followed by "
                  f"DRY, DRY_ALL or APPLY, e.g. \"{marker}APPLY a1b2c3d4e5f6\""),
        )

    rest = line[1:]
    parts = rest.split()
    if not parts:
        raise DeckSyntaxError(
            "deck must start with DRY, DRY_ALL or APPLY",
            hint=f"first line must be a header like \"{marker}APPLY <rev>\".",
        )

    cmd = parts[0]
    if cmd not in HEADER_NAMES:
        raise DeckSyntaxError(
            "deck must start with DRY, DRY_ALL or APPLY",
            hint=(f"\"{marker}{cmd}\" is not a header; use \"{marker}APPLY\", "
                  f"\"{marker}DRY\" or \"{marker}DRY_ALL\" with a <rev>"),
        )

    rev = parts[1] if len(parts) > 1 else None
    if rev is None:
        raise DeckSyntaxError(
            '<rev> is mandatory for existing files',
            hint=(f"add the current REV after the command, e.g. "
                  f"\"{marker}APPLY a1b2c3d4e5f6\" (get it from deck_get)"),
        )
    if len(rev) != 16 or not all(c in '0123456789abcdef' for c in rev):
        raise DeckSyntaxError(
            'invalid <rev> format',
            hint=(f"<rev> is exactly 16 hex chars (0-9a-f), e.g. "
                  f"\"{marker}APPLY a1b2c3d4e5f6\""),
        )
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
                raise DeckSyntaxError(
                    "operation after SKIP",
                    hint=("`SKIP` must be the last operation; everything after it is "
                          "payload. Move other operations before it."),
                )
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
            raise DeckSyntaxError(
                "unexpected line — expected command or payload",
                hint=(f"after a command, payload lines follow until the next "
                      f"\"{marker}\" line or \"{marker}END\"."),
            )

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

    Строка команды полностью разбирается грамматикой:
      <marker> <op> [<address>] [SKIP]
    Всё лишнее после адреса (кроме SKIP) — ошибка, потому что у команды
    нет «хвоста», а новый текст лежит на следующих строках.
    """
    line = lines[start].strip()
    # Убираем маркер
    rest = line[1:]
    parts = rest.split()

    if not parts:
        raise DeckSyntaxError(
            "deck must start with DRY, DRY_ALL or APPLY",
            hint=f"command lines must start with the marker \"{marker}\", e.g. \"{marker}REPLACE 5\".",
        )

    op_name = parts[0]

    # Fast-Fail: проверяем, что команда известна
    if op_name not in OPERATION_NAMES:
        raise DeckSyntaxError(
            f"unknown operation: {op_name}",
            hint=("valid operations are REPLACE, DELETE, INSERT, INSERT_HEAD, "
                  f"REPLACE_REGEX, APPEND — write \"{marker}{op_name}\" using one of them"),
        )

    address = None
    skip = False
    rest_tokens = parts[1:]

    if op_name == "INSERT_HEAD":
        # INSERT_HEAD — без адреса, но SKIP разрешён
        if rest_tokens:
            if len(rest_tokens) == 1 and rest_tokens[0] == "SKIP":
                skip = True
            else:
                raise DeckSyntaxError(
                    "INSERT_HEAD takes no address",
                    hint=(f"\"{marker}INSERT_HEAD\" takes no address; only an optional "
                          f"SKIP is allowed — write \"{marker}INSERT_HEAD\" or "
                          f"\"{marker}INSERT_HEAD SKIP\"."),
                )
    elif op_name == "APPEND":
        # APPEND — ни адреса, ни SKIP
        if rest_tokens:
            raise DeckSyntaxError(
                "APPEND takes no address",
                hint=(f"\"{marker}APPEND\" takes no address and no SKIP — "
                      f"write only \"{marker}APPEND\"."),
            )
    else:
        # REPLACE / DELETE / INSERT / REPLACE_REGEX — адрес (опц.) + SKIP (опц.)
        if rest_tokens:
            if rest_tokens[0] == "SKIP":
                raise DeckSyntaxError(
                    f"{op_name} requires an address",
                    hint=(f"write \"{marker}{op_name} <address>[SKIP]\", e.g. "
                          f"\"{marker}{op_name} 5\""),
                )
            address = Address.parse(rest_tokens[0])
            remaining = rest_tokens[1:]
            if remaining:
                if len(remaining) == 1 and remaining[0] == "SKIP":
                    skip = True
                elif remaining[0] == "SKIP":
                    raise DeckSyntaxError(
                        "SKIP takes no arguments",
                        hint=("SKIP is a boolean flag with no arguments — write "
                              f"\"{marker}{op_name} 5 SKIP\", not "
                              f"\"{marker}{op_name} 5 SKIP 3\"."),
                    )
                else:
                    raise DeckSyntaxError(
                        f'unexpected token "{remaining[0]}" after address in {marker}{op_name}',
                        hint=(f"a command line is fully the command "
                              f"\"{marker}{op_name} <address> [SKIP]\"; put new text on "
                              f"the following lines — Deck edits whole lines, not characters"),
                    )

    payload_start = start + 1

    # Fast-Fail: DELETE не должен иметь SKIP (spec §6, §11) — проверяем ДО payload
    if op_name == "DELETE" and skip:
        raise DeckSyntaxError(
            "DELETE does not support SKIP",
            hint=f"\"{marker}DELETE\" takes an address only, no SKIP — e.g. \"{marker}DELETE 5\".",
        )

    # Fast-Fail: REPLACE_REGEX не должен иметь SKIP (payload всегда идёт до END)
    if op_name == "REPLACE_REGEX" and skip:
        raise DeckSyntaxError(
            "REPLACE_REGEX does not support SKIP",
            hint=(f"\"{marker}REPLACE_REGEX\" payload runs to "
                  f"\"{marker}END\" and takes no SKIP — e.g. \"{marker}REPLACE_REGEX 1-10\"."),
        )

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
        # Если дошёл до конца без терминатора — вернём len(lines)
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

    # DELETE — Fast-Fail: если есть хоть одна строка payload, бросаем немедленно
    if op_name == "DELETE":
        idx = payload_start
        while idx < len(lines) - 1:
            next_line = lines[idx].strip()
            if _is_command(next_line, marker) or _is_terminator(next_line, marker):
                return op, idx
            # Первая строка payload — ошибка, бросаем немедленно
            raise DeckSyntaxError(
                "unexpected payload after DELETE",
                hint=f"\"{marker}DELETE\" has no payload — delete by address only, e.g. \"{marker}DELETE 5\".",
            )
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
