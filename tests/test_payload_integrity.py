"""Юнит-тесты целостности payload (неизменяемость карт payload).

Фундаментальное правило Deck: всё, что модель передаёт как новый текст
(payload команд REPLACE/INSERT/INSERT_HEAD/APPEND и поток CREATE), должно
быть записано в файл СТРОГО БЕЗ ИЗМЕНЕНИЙ.

Категорически запрещено:
  - убирать лидирующие пробелы/табы (в том числе у ПЕРВОЙ строки payload);
  - убирать конечные пробелы/табы;
  - менять пробелы и табы местами или сжимать их;
  - обрезать, добавлять или менять переводы строки;
  - менять кодировку, BOM, любые байты.

Payload-карта должна пройти путь «текст колоды -> парсер -> операция ->
применение -> файл» идентично себе (за исключением того, что операция
дописывает перевед строки, которого нет в исходном тексте колоды).

Эти тесты — регрессионная защита и одновременно средство обнарущения бага,
когда Deck модифицирует payload (в частности — лидирующие пробелы первой
карты).
"""


import pytest

from deck_editor.parser import Address, Operation, parse_deck
from deck_editor.operations import apply_operation
from deck_editor.apply import apply as apply_impl
from deck_editor.utils import compute_xxhash, compute_content_hash


# ---------------------------------------------------------------------------
# Строки payload, которые нельзя портить. Первая строка всегда с отступом,
# чтобы отдельно ловить «съедание» лидирующих пробелов первой карты.
# ---------------------------------------------------------------------------

FIRST_WITH_SPACES = "    indented first line"
SECOND_WITH_SPACES = "    second indented line"

FIRST_WITH_TABS = "\t\tfirst with tabs"
SECOND_WITH_TABS = "\tsecond with tabs"

FIRST_WITH_TRAILING = "trailing first   "
SECOND_WITH_TRAILING = "trailing second\t"

WHITESPACE_ONLY = "   "

FIRST_EMPTY = ""
SECOND_PLAIN = "plain second"

ORIGINAL = ["line1\n", "line2\n", "line3\n"]

REV_3_LINES = "3b52a31d46cf14bc"


def _payload(*lines):
    """Собирает payload без переводов строк (как в тексте колоды)."""
    return list(lines)


class TestPayloadIntegrity:
    """Payload не должен изменяться ни на этапе парсинга, ни на применении."""

    # ------------------------------------------------------------------
    # Парсер: строки payload сохраняются бит-в-бит
    # ------------------------------------------------------------------

    def test_parse_replace_first_line_leading_spaces(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@REPLACE 1\n"
            f"{FIRST_WITH_SPACES}\n"
            f"{SECOND_WITH_SPACES}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(FIRST_WITH_SPACES, SECOND_WITH_SPACES)

    def test_parse_replace_first_line_tabs(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@REPLACE 1\n"
            f"{FIRST_WITH_TABS}\n"
            f"{SECOND_WITH_TABS}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(FIRST_WITH_TABS, SECOND_WITH_TABS)

    def test_parse_replace_trailing_whitespace_preserved(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@REPLACE 1\n"
            f"{FIRST_WITH_TRAILING}\n"
            f"{SECOND_WITH_TRAILING}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(FIRST_WITH_TRAILING, SECOND_WITH_TRAILING)

    def test_parse_replace_whitespace_only_first_line(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@REPLACE 1\n"
            f"{WHITESPACE_ONLY}\n"
            f"{SECOND_PLAIN}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(WHITESPACE_ONLY, SECOND_PLAIN)

    def test_parse_replace_empty_first_line(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@REPLACE 1\n"
            f"{FIRST_EMPTY}\n"
            f"{SECOND_PLAIN}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(FIRST_EMPTY, SECOND_PLAIN)

    def test_parse_insert_first_line_leading_spaces(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@INSERT 2\n"
            f"{FIRST_WITH_SPACES}\n"
            f"{SECOND_WITH_SPACES}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(FIRST_WITH_SPACES, SECOND_WITH_SPACES)

    def test_parse_insert_head_first_line_leading_spaces(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@INSERT_HEAD\n"
            f"{FIRST_WITH_SPACES}\n"
            f"{SECOND_WITH_SPACES}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(FIRST_WITH_SPACES, SECOND_WITH_SPACES)

    def test_parse_append_first_line_leading_spaces(self):
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@APPEND\n"
            f"{FIRST_WITH_SPACES}\n"
            f"{SECOND_WITH_SPACES}\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.payload == _payload(FIRST_WITH_SPACES, SECOND_WITH_SPACES)

    def test_parse_skip_first_line_leading_spaces(self):
        # SKIP: payload идёт до терминатора, даже если строки выглядят как команды
        deck = (
            f"@DRY {REV_3_LINES}\n"
            "@REPLACE 1 SKIP\n"
            f"{FIRST_WITH_SPACES}\n"
            "@REPLACE 99\n"
            "@END\n"
        )
        op = parse_deck(deck).operations[0]
        assert op.skip is True
        assert op.payload[0] == FIRST_WITH_SPACES

    # ------------------------------------------------------------------
    # Применение: payload записывается без изменений (кроме \n)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "op_name,addr",
        [
            ("REPLACE", "1"),
            ("INSERT", "2"),
            ("INSERT_HEAD", None),
            ("APPEND", None),
        ],
    )
    def test_apply_operation_preserves_first_line(self, op_name, addr):
        address = Address.parse(addr) if addr is not None else None
        op = Operation(
            name=op_name,
            address=address,
            payload=_payload(FIRST_WITH_SPACES, SECOND_WITH_SPACES),
        )
        result = apply_operation(ORIGINAL, op)
        # Каждая строка payload должна появиться с дописанным \n и без изменений
        assert f"{FIRST_WITH_SPACES}\n" in result
        assert f"{SECOND_WITH_SPACES}\n" in result

    def test_apply_operation_preserves_tabs_first_line(self):
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=_payload(FIRST_WITH_TABS, SECOND_WITH_TABS),
        )
        result = apply_operation(ORIGINAL, op)
        assert f"{FIRST_WITH_TABS}\n" in result
        assert f"{SECOND_WITH_TABS}\n" in result

    def test_apply_operation_preserves_trailing_whitespace(self):
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=_payload(FIRST_WITH_TRAILING, SECOND_WITH_TRAILING),
        )
        result = apply_operation(ORIGINAL, op)
        assert f"{FIRST_WITH_TRAILING}\n" in result
        assert f"{SECOND_WITH_TRAILING}\n" in result

    def test_apply_operation_preserves_whitespace_only_first_line(self):
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=_payload(WHITESPACE_ONLY, SECOND_PLAIN),
        )
        result = apply_operation(ORIGINAL, op)
        assert f"{WHITESPACE_ONLY}\n" in result
        assert f"{SECOND_PLAIN}\n" in result

    def test_apply_operation_preserves_empty_first_line(self):
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=_payload(FIRST_EMPTY, SECOND_PLAIN),
        )
        result = apply_operation(ORIGINAL, op)
        assert "\n" in result
        assert f"{SECOND_PLAIN}\n" in result

    # ------------------------------------------------------------------
    # Полный round-trip через APPLY к реальному файлу
    # ------------------------------------------------------------------

    def test_apply_roundtrip_file_preserves_first_line(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("line1\nline2\nline3\n", encoding="utf-8")
        deck_text = (
            f"@APPLY {REV_3_LINES}\n"
            "@REPLACE 1\n"
            f"{FIRST_WITH_TABS}\n"
            f"{FIRST_WITH_TRAILING}\n"
            f"{WHITESPACE_ONLY}\n"
            "@END\n"
        )
        deck = parse_deck(deck_text)
        apply_impl(str(target), deck, str(tmp_path))

        written = target.read_text(encoding="utf-8")
        lines = written.splitlines()
        assert lines[0] == FIRST_WITH_TABS
        assert lines[1] == FIRST_WITH_TRAILING
        assert lines[2] == WHITESPACE_ONLY

    def test_no_payload_line_is_stripped_of_leading_spaces(self, tmp_path):
        # Каждая карта payload — с разным отступом; ни одна не должна быть
        # сдвигана влево.
        target = tmp_path / "file.txt"
        target.write_text("line1\nline2\n", encoding="utf-8")
        rev = compute_xxhash(str(target))
        a = "   x"
        b = "      y"
        c = "\tz"
        deck_text = (
            f"@APPLY {rev}\n"
            "@REPLACE 1\n"
            f"{a}\n"
            f"{b}\n"
            f"{c}\n"
            "@END\n"
        )
        deck = parse_deck(deck_text)
        apply_impl(str(target), deck, str(tmp_path))

        written = target.read_text(encoding="utf-8")
        lines = written.splitlines()
        assert lines[0] == a
        assert lines[1] == b
        assert lines[2] == c

    # ------------------------------------------------------------------
    # Регрессия: срезание первой строки меняет REV результата.
    #
    # Этот тест прямо кодирует доказательство, которое ловит галлюцинацию:
    # применяемое содержимое должно совпадать с ожидаемым (отступ сохранён),
    # а хеш (REV) полученного файла — НЕ совпадать с хешем «срезанного»
    # варианта. Если код начнёт резать лидирующие пробелы первой строки,
    # REV изменится и тест упадёт.
    # ------------------------------------------------------------------

    def test_stripping_first_line_changes_rev(self, tmp_path):
        indented_first = "        s1"   # 8 пробелов
        other = "        s2"            # 8 пробелов (сохраняется всегда)

        target = tmp_path / "file.txt"
        target.write_text("a\nb\nc\n", encoding="utf-8")
        rev = compute_xxhash(str(target))
        deck_text = (
            f"@APPLY {rev}\n"
            "@REPLACE 1-3\n"
            f"{indented_first}\n"
            f"{other}\n"
            f"{other}\n"
            "@END\n"
        )
        deck = parse_deck(deck_text)
        apply_impl(str(target), deck, str(tmp_path))

        written = target.read_text(encoding="utf-8")
        expected = f"{indented_first}\n{other}\n{other}\n"

        # 1. Применяемое содержимое равно ожидаемому (отступ первой строки на месте).
        assert written == expected

        # 2. Хеш («REV») реального результата отличается от хеша «срезанного»
        #    варианта — значит, любое срезание первой строки будет ловиться по REV.
        stripped = "s1\n" + f"{other}\n{other}\n"
        assert compute_content_hash(written) != compute_content_hash(stripped)
