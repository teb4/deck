"""Тесты для повышения покрытия parser.py до 100%.

Покрываются непокрытые ветки:
- __repr__ для Address, Operation, Deck
- to_tuple для Address
- _is_terminator с marker (когда marker указан и строка не начинается с него)
- _parse_terminator error (пустая строка)
- _parse_header error paths (пустая строка, пустой rest)
- _validate_parsed_operations ветки (INSERT single line address, INSERT_HEAD с address, range start > end)
- _parse_operations – operation after SKIP, unexpected line
- _parse_operation – DELETE payload, SKIP args, INSERT_HEAD с адресом, REPLACE с payload после терминатора
"""

import pytest
from pytest import raises

from deck_editor.parser import (
    Address,
    Deck,
    Operation,
    parse_deck,
    _is_terminator,
    _parse_header,
    _parse_terminator,
)
from deck_editor.utils import DeckSyntaxError


class TestRepr:
    """Тесты __repr__ методов."""

    def test_address_repr_single(self):
        addr = Address.parse("5")
        assert repr(addr) == "Address(5)"

    def test_address_repr_range(self):
        addr = Address.parse("5-10")
        assert repr(addr) == "Address(5-10)"

    def test_address_repr_to_end(self):
        addr = Address.parse("5-")
        assert repr(addr) == "Address(5-)"

    def test_operation_repr_no_skip(self):
        op = Operation(name="REPLACE", address=Address.parse("5"), skip=False, payload=["test"])
        assert repr(op) == "Op(REPLACE 5, payload=1 lines)"

    def test_operation_repr_with_skip(self):
        op = Operation(name="REPLACE", address=Address.parse("5"), skip=True, payload=["test"])
        assert repr(op) == "Op(REPLACE 5 SKIP, payload=1 lines)"

    def test_operation_repr_no_address(self):
        op = Operation(name="INSERT_HEAD", address=None, skip=False, payload=["test"])
        assert repr(op) == "Op(INSERT_HEAD, payload=1 lines)"

    def test_deck_repr_no_ops(self):
        deck = Deck(mode="APPLY", rev="abcdef1234567890")
        assert repr(deck) == "Deck(APPLY, rev=abcdef1234567890, ops=0)"

    def test_deck_repr_with_ops(self):
        deck = Deck(
            mode="DRY",
            rev="1234567890abcdef",
            operations=[
                Operation(name="REPLACE", address=Address.parse("1"), payload=["test"]),
            ],
        )
        assert repr(deck) == "Deck(DRY, rev=1234567890abcdef, ops=1)"


class TestIsTerminator:
    """Тесты _is_terminator с marker."""

    def test_terminator_at(self):
        assert _is_terminator("@END", "@") is True

    def test_terminator_dollar(self):
        assert _is_terminator("$END", "$") is True

    def test_terminator_any_marker(self):
        assert _is_terminator("@END", None) is True
        assert _is_terminator("$END", None) is True

    def test_terminator_wrong_marker(self):
        # marker=@, но строка начинается с $ — не терминатор
        assert _is_terminator("$END", "@") is False

    def test_terminator_empty(self):
        assert _is_terminator("", "@") is False

    def test_terminator_not_end(self):
        assert _is_terminator("@REPLACE 5", "@") is False
        assert _is_terminator("@INSERT 5", "@") is False

    def test_terminator_no_marker(self):
        assert _is_terminator("END", "@") is False


class TestParseTerminator:
    """Тесты _parse_terminator."""

    def test_parse_terminator_at(self):
        marker, cmd = _parse_terminator("@END", None)
        assert marker == "@"
        assert cmd == "END"

    def test_parse_terminator_dollar(self):
        marker, cmd = _parse_terminator("$END", None)
        assert marker == "$"
        assert cmd == "END"

    def test_parse_terminator_empty(self):
        with raises(DeckSyntaxError) as exc_info:
            _parse_terminator("", None)
        assert "deck not terminated by END" in str(exc_info.value)


class TestParseHeaderErrors:
    """Тесты ошибок _parse_header."""

    def test_parse_header_empty(self):
        with raises(DeckSyntaxError) as exc_info:
            _parse_header("")
        assert "deck must start with DRY, DRY_ALL or APPLY" in str(exc_info.value)

    def test_parse_header_no_marker(self):
        with raises(DeckSyntaxError) as exc_info:
            _parse_header("DRY abcdef1234567890")
        assert "deck must start with DRY, DRY_ALL or APPLY" in str(exc_info.value)

    def test_parse_header_only_marker(self):
        with raises(DeckSyntaxError) as exc_info:
            _parse_header("@")
        assert "deck must start with DRY, DRY_ALL or APPLY" in str(exc_info.value)

    def test_parse_header_invalid_cmd(self):
        with raises(DeckSyntaxError) as exc_info:
            _parse_header("@FOO abcdef1234567890")
        assert "deck must start with DRY, DRY_ALL or APPLY" in str(exc_info.value)


class TestValidateParsedOperations:
    """Тесты _validate_parsed_operations (внутри parser.py)."""

    def test_validate_insert_single_line_ok(self):
        """INSERT с одиночным адресом — валидно."""
        from deck_editor.parser import _validate_parsed_operations
        ops = [Operation(name="INSERT", address=Address.parse("5"), skip=False, payload=["test"])]
        _validate_parsed_operations(ops)

    def test_validate_insert_head_no_address_ok(self):
        """INSERT_HEAD без address — валидно."""
        from deck_editor.parser import _validate_parsed_operations
        ops = [Operation(name="INSERT_HEAD", address=None, skip=False, payload=["test"])]
        _validate_parsed_operations(ops)

    def test_validate_insert_head_with_address_error(self):
        """INSERT_HEAD с address — ошибка (приоритет 9)."""
        from deck_editor.parser import _validate_parsed_operations
        ops = [Operation(name="INSERT_HEAD", address=Address.parse("5"), skip=False, payload=["test"])]
        with raises(DeckSyntaxError) as exc_info:
            _validate_parsed_operations(ops)
        assert "INSERT_HEAD takes no address" in str(exc_info.value)

    def test_validate_address_range_start_gt_end(self):
        """REPLACE 10-5 — ошибка (приоритет 11)."""
        from deck_editor.parser import _validate_parsed_operations
        ops = [Operation(name="REPLACE", address=Address.parse("10-5"), skip=False, payload=["test"])]
        with raises(DeckSyntaxError) as exc_info:
            _validate_parsed_operations(ops)
        assert "invalid address range — start > end" in str(exc_info.value)


class TestParseDeckOperationEdgeCases:
    """Тесты edge cases _parse_operation."""

    def test_parse_deck_delete_with_payload_error(self):
        """DELETE с payload — ошибка на этапе парсинга (приоритет 5)."""
        text = """@APPLY abcdef1234567890
@DELETE 5
эта строка не должна быть здесь
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "unexpected payload after DELETE" in str(exc_info.value)

    def test_parse_deck_insert_head_with_address_error(self):
        """INSERT_HEAD с адресом — ошибка (приоритет 9)."""
        text = """@APPLY abcdef1234567890
@INSERT_HEAD 5
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "INSERT_HEAD takes no address" in str(exc_info.value)

    def test_parse_deck_skip_with_args_error(self):
        """SKIP с аргументами — ошибка (приоритет 6)."""
        text = """@APPLY abcdef1234567890
@REPLACE 5 SKIP 3
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "SKIP takes no arguments" in str(exc_info.value)

    def test_parse_deck_replace_skip_with_args_error(self):
        """REPLACE N SKIP M — ошибка SKIP takes no arguments."""
        text = """@APPLY abcdef1234567890
@REPLACE 5-10 SKIP 3
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "SKIP takes no arguments" in str(exc_info.value)

    def test_parse_deck_operation_after_skip(self):
        """После SKIP всё до @END — payload (парсер не ищет команды)."""
        text = """@APPLY abcdef1234567890
@REPLACE 5 SKIP
@REPLACE 10
@INSERT 20
@END"""
        deck = parse_deck(text)
        assert len(deck.operations) == 1
        assert deck.operations[0].name == "REPLACE"
        assert deck.operations[0].address.start == 5
        assert deck.operations[0].skip is True
        assert deck.operations[0].payload == ["@REPLACE 10", "@INSERT 20"]

    def test_parse_deck_unexpected_line(self):
        """Строка без маркера после заголовка — ошибка."""
        text = """@APPLY abcdef1234567890
эта строка без маркера
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "unexpected line" in str(exc_info.value)

    def test_parse_deck_unexpected_line_after_ops(self):
        """Строка без маркера после REPLACE — payload (парсер сканирует до следующей команды)."""
        text = """@APPLY abcdef1234567890
@REPLACE 5
новая строка
эта строка без маркера
@END"""
        deck = parse_deck(text)
        assert len(deck.operations) == 1
        assert deck.operations[0].payload == ["новая строка", "эта строка без маркера"]

    def test_parse_deck_insert_with_range_error(self):
        """INSERT с диапазоном — ошибка (приоритет 8)."""
        text = """@APPLY abcdef1234567890
@INSERT 5-10
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "INSERT requires single line address" in str(exc_info.value)

    def test_parse_deck_replace_to_end(self):
        """REPLACE с адресом N- (до конца файла)."""
        text = """@APPLY abcdef1234567890
@REPLACE 2-
новая строка A
новая строка B
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].address.start == 2
        assert deck.operations[0].address.is_to_end is True
        assert deck.operations[0].payload == ["новая строка A", "новая строка B"]

    def test_parse_deck_multiple_replace_with_skip(self):
        """REPLACE с SKIP в конце колоды."""
        text = """@APPLY abcdef1234567890
@REPLACE 5
новая строка
@REPLACE 10 SKIP
@REPLACE 15
@END"""
        deck = parse_deck(text)
        assert len(deck.operations) == 2
        assert deck.operations[0].name == "REPLACE"
        assert deck.operations[0].address.start == 5
        assert deck.operations[0].payload == ["новая строка"]
        assert deck.operations[1].name == "REPLACE"
        assert deck.operations[1].address.start == 10
        assert deck.operations[1].skip is True
        assert deck.operations[1].payload == ["@REPLACE 15"]

    def test_parse_deck_dollar_marker_operations(self):
        """Колода с маркером $."""
        text = """$DRY abcdef1234567890
$REPLACE 5
новая строка
$END"""
        deck = parse_deck(text)
        assert deck.mode == "DRY"
        assert deck.marker == "$"
        assert deck.operations[0].name == "REPLACE"
        assert deck.operations[0].address.start == 5

    def test_parse_deck_mixed_marker_error(self):
        """Терминатор $END при заголовке @APPLY — ошибка."""
        text = """@APPLY abcdef1234567890
@REPLACE 5
новая строка
$END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "terminator does not match deck marker" in str(exc_info.value)

    def test_parse_deck_empty_payload_replace(self):
        """REPLACE с пустым payload (удаление строки)."""
        text = """@APPLY abcdef1234567890
@REPLACE 5
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "REPLACE"
        assert deck.operations[0].payload == []

    def test_parse_deck_insert_head_no_payload(self):
        """INSERT_HEAD без payload."""
        text = """@APPLY abcdef1234567890
@INSERT_HEAD
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "INSERT_HEAD"
        assert deck.operations[0].payload == []

    def test_parse_deck_rev_invalid_format(self):
        """REV с неправильным форматом — ошибка."""
        text = """@APPLY abcdef123456789
@REPLACE 5
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "invalid <rev> format" in str(exc_info.value)

    def test_parse_deck_rev_too_long(self):
        """REV длиннее 16 символов — ошибка."""
        text = """@APPLY abcdef12345678901
@REPLACE 5
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "invalid <rev> format" in str(exc_info.value)

    def test_parse_deck_rev_uppercase(self):
        """REV с заглавными буквами — ошибка (только строчные hex)."""
        text = """@APPLY ABCDEF1234567890
@REPLACE 5
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "invalid <rev> format" in str(exc_info.value)

    def test_parse_deck_rev_special_chars(self):
        """REV с спецсимволами — ошибка."""
        text = """@APPLY abcdef123456789g
@REPLACE 5
новая строка
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "invalid <rev> format" in str(exc_info.value)

    def test_parse_deck_multiple_operations_mixed(self):
        """Колода с DELETE, REPLACE, INSERT, INSERT_HEAD."""
        text = """@APPLY abcdef1234567890
@DELETE 10-15
@REPLACE 5
новая пятая
@INSERT 20
новая после 20
@INSERT_HEAD
в самое начало
@END"""
        deck = parse_deck(text)
        assert len(deck.operations) == 4
        assert deck.operations[0].name == "DELETE"
        assert deck.operations[1].name == "REPLACE"
        assert deck.operations[2].name == "INSERT"
        assert deck.operations[3].name == "INSERT_HEAD"

    def test_parse_deck_insert_head_skip_at_in_payload(self):
        """INSERT_HEAD с SKIP и @ в payload."""
        text = """@APPLY abcdef1234567890
@INSERT_HEAD SKIP
@app.route("/api")
def view():
    pass
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "INSERT_HEAD"
        assert deck.operations[0].skip is True
        assert deck.operations[0].payload == ['@app.route("/api")', "def view():", "    pass"]

    def test_parse_deck_replace_multiline_payload(self):
        """REPLACE с многострочным payload."""
        text = """@APPLY abcdef1234567890
@REPLACE 1
line one
line two
line three
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].payload == ["line one", "line two", "line three"]

    def test_parse_deck_address_start_gt_end_in_range(self):
        """REPLACE 10-5 — start > end, ошибка на этапе парсинга."""
        text = """@APPLY abcdef1234567890
@REPLACE 10-5
новая
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "invalid address range — start > end" in str(exc_info.value)

    def test_parse_deck_delete_with_skip_error(self):
        """DELETE с SKIP — ошибка (spec §6, §11)."""
        text = """@APPLY abcdef1234567890
@DELETE 5 SKIP
@END"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(text)
        assert "DELETE does not support SKIP" in str(exc_info.value)
