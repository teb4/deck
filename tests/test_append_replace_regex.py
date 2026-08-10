"""Тесты для операций REPLACE_REGEX и APPEND."""

import pytest
from pytest import raises

from deck_editor.parser import parse_deck
from deck_editor.operations import apply_operation, validate_operations
from deck_editor.parser import Address, Operation
from deck_editor.utils import DeckSyntaxError


class TestReplaceRegex:
    """Тесты REPLACE_REGEX — regex-замена по sed-синтаксису."""

    def test_replace_regex_simple(self):
        """Замена foo на bar в строке 2."""
        lines = ["строка 1\n", "foo\n", "строка 3\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("2"),
            payload=["s/foo/bar/"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "bar\n", "строка 3\n"]

    def test_replace_regex_range(self):
        """Замена foo на bar в строках 1-2."""
        lines = ["foo\n", "foo\n", "строка 3\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1-2"),
            payload=["s/foo/bar/"],
        )
        result = apply_operation(lines, op)
        assert result == ["bar\n", "bar\n", "строка 3\n"]

    def test_replace_regex_to_end(self):
        """Замена foo на bar от строки 2 до конца."""
        lines = ["строка 1\n", "foo\n", "foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("2-"),
            payload=["s/foo/bar/"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "bar\n", "bar\n"]

    def test_replace_regex_capture_group(self):
        """Замена с захватом групп: (foo) → BAR_\\1."""
        lines = ["foo\n", "baz\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s/(foo)/BAR_\\1/"],
        )
        result = apply_operation(lines, op)
        assert result == ["BAR_foo\n", "baz\n"]

    def test_replace_regex_no_match(self):
        """Если regex не совпадает — строка остаётся без изменений."""
        lines = ["строка 1\n", "baz\n", "строка 3\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("2"),
            payload=["s/foo/bar/"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "baz\n", "строка 3\n"]

    def test_replace_regex_global(self):
        """Флаг g — замена всех совпадений в строке."""
        lines = ["foo bar foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s/foo/baz/g"],
        )
        result = apply_operation(lines, op)
        assert result == ["baz bar baz\n"]

    def test_replace_regex_global_simple(self):
        """Флаг g — простая замена всех foo на bar."""
        lines = ["foo bar foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s/foo/bar/g"],
        )
        result = apply_operation(lines, op)
        assert result == ["bar bar bar\n"]

    def test_replace_regex_no_global(self):
        """Без флага g — только первое совпадение."""
        lines = ["foo bar foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s/foo/baz/"],
        )
        result = apply_operation(lines, op)
        assert result == ["baz bar foo\n"]

    def test_replace_regex_pipe_delimiter(self):
        """Разделитель | вместо /."""
        lines = ["foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s|foo|bar|"],
        )
        result = apply_operation(lines, op)
        assert result == ["bar\n"]

    def test_replace_regex_hash_delimiter(self):
        """Разделитель #."""
        lines = ["foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s#foo#bar#"],
        )
        result = apply_operation(lines, op)
        assert result == ["bar\n"]

    def test_replace_regex_tilde_delimiter(self):
        """Разделитель ~."""
        lines = ["foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s~foo~bar~"],
        )
        result = apply_operation(lines, op)
        assert result == ["bar\n"]

    def test_replace_regex_invalid_delimiter(self):
        """Неподдерживаемый разделитель."""
        lines = ["foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload="sfoo/bar/",
        )
        with pytest.raises(DeckSyntaxError):
            apply_operation(lines, op)

    def test_replace_regex_empty_payload(self):
        """Пустой payload — ошибка."""
        lines = ["foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=[],
        )
        with pytest.raises(DeckSyntaxError):
            apply_operation(lines, op)

    def test_replace_regex_single_line(self):
        """REPLACE_REGEX с адресом N (одна строка)."""
        lines = ["foo\n", "baz\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s/foo/bar/"],
        )
        result = apply_operation(lines, op)
        assert result == ["bar\n", "baz\n"]

    def test_replace_regex_range_expand(self):
        """REPLACE_REGEX: диапазон строк остаётся той же длины (M→M)."""
        lines = ["foo\n", "foo\n", "baz\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1-2"),
            payload=["s/foo/bar/"],
        )
        result = apply_operation(lines, op)
        assert len(result) == 3
        assert result[0] == "bar\n"
        assert result[1] == "bar\n"
        assert result[2] == "baz\n"

    def test_replace_regex_special_chars(self):
        """Спецсимволы в replacement: \\1 — backreference."""
        lines = ["foo\n"]
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s/(foo)/\\1/"],
        )
        result = apply_operation(lines, op)
        # \\1 — это backreference на группу (foo), т.е. 'foo'
        assert result == ["foo\n"]


class TestAppend:
    """Тесты APPEND — добавление строк в конец файла."""

    def test_append_single_line(self):
        """Добавление одной строки в конец."""
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="APPEND",
            address=None,
            payload=["новая строка"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "строка 2\n", "новая строка\n"]

    def test_append_multiple_lines(self):
        """Добавление нескольких строк."""
        lines = ["строка 1\n"]
        op = Operation(
            name="APPEND",
            address=None,
            payload=["новая 1", "новая 2", "новая 3"],
        )
        result = apply_operation(lines, op)
        assert result == [
            "строка 1\n",
            "новая 1\n",
            "новая 2\n",
            "новая 3\n",
        ]

    def test_append_empty_file(self):
        """APPEND к пустому файлу."""
        lines: list[str] = []
        op = Operation(
            name="APPEND",
            address=None,
            payload=["новая строка"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая строка\n"]

    def test_append_preserves_existing(self):
        """APPEND не изменяет существующие строки."""
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="APPEND",
            address=None,
            payload=["новая строка"],
        )
        result = apply_operation(lines, op)
        assert result[0] == "строка 1\n"
        assert result[1] == "строка 2\n"

    def test_append_no_trailing_newline(self):
        """Если payload не имеет \\n — добавляется."""
        lines = ["строка 1\n"]
        op = Operation(
            name="APPEND",
            address=None,
            payload=["новая строка"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая строка\n"]

    def test_append_preserves_trailing_newline(self):
        """Если payload уже имеет \\n — не дублируется."""
        lines = ["строка 1\n"]
        op = Operation(
            name="APPEND",
            address=None,
            payload=["новая строка\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая строка\n"]

    def test_append_json(self):
        """APPEND JSON-объекта (типичный кейс)."""
        lines: list[str] = []
        op = Operation(
            name="APPEND",
            address=None,
            payload=['{"sensor": "temp", "value": 30.0, "unit": "C"}'],
        )
        result = apply_operation(lines, op)
        assert result == ['{"sensor": "temp", "value": 30.0, "unit": "C"}\n']

    def test_append_multiple_json(self):
        """APPEND нескольких JSON-объектов."""
        lines: list[str] = []
        op = Operation(
            name="APPEND",
            address=None,
            payload=[
                '{"sensor": "temp", "value": 30.0}',
                '{"sensor": "humidity", "value": 65.0}',
            ],
        )
        result = apply_operation(lines, op)
        assert len(result) == 2
        assert '{"sensor": "temp"' in result[0]
        assert '{"sensor": "humidity"' in result[1]


class TestParseReplaceRegex:
    """Тесты парсинга REPLACE_REGEX."""

    def test_parse_replace_regex(self):
        text = """@APPLY abcdef1234567890
@REPLACE_REGEX 1-5
s/foo/bar/g
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "REPLACE_REGEX"
        assert deck.operations[0].address.start == 1
        assert deck.operations[0].address.end == 5
        assert deck.operations[0].payload == ["s/foo/bar/g"]

    def test_parse_replace_regex_single(self):
        text = """@APPLY abcdef1234567890
@REPLACE_REGEX 3
s/temp/\\1_celsius/g
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "REPLACE_REGEX"
        assert deck.operations[0].address.start == 3
        assert deck.operations[0].payload == ["s/temp/\\1_celsius/g"]

    def test_parse_replace_regex_to_end(self):
        text = """@APPLY abcdef1234567890
@REPLACE_REGEX 10-
s/old/new/g
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "REPLACE_REGEX"
        assert deck.operations[0].address.is_to_end is True

    def test_parse_replace_regex_no_address(self):
        """REPLACE_REGEX без адреса — ошибка."""
        text = """@APPLY abcdef1234567890
@REPLACE_REGEX
s/foo/bar/g
@END"""
        with raises(DeckSyntaxError):
            parse_deck(text)

    def test_parse_replace_regex_with_skip(self):
        """REPLACE_REGEX с SKIP (payload содержит @ на нулевой колонке)."""
        text = """@APPLY abcdef1234567890
@REPLACE_REGEX 1-10 SKIP
s/@user/@admin/g
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "REPLACE_REGEX"
        assert deck.operations[0].skip is True
        assert deck.operations[0].payload == ["s/@user/@admin/g"]


class TestParseAppend:
    """Тесты парсинга APPEND."""

    def test_parse_append(self):
        text = """@APPLY abcdef1234567890
@APPEND
{"sensor": "temp", "value": 30.0}
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "APPEND"
        assert deck.operations[0].address is None
        assert deck.operations[0].payload == ['{"sensor": "temp", "value": 30.0}']

    def test_parse_append_multiple_lines(self):
        text = """@APPLY abcdef1234567890
@APPEND
строка 1
строка 2
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "APPEND"
        assert deck.operations[0].payload == ["строка 1", "строка 2"]

    def test_parse_append_no_address(self):
        """APPEND с адресом — ошибка."""
        text = """@APPLY abcdef1234567890
@APPEND 5
новая строка
@END"""
        with raises(DeckSyntaxError):
            parse_deck(text)

    def test_parse_append_with_skip(self):
        """APPEND с SKIP — ошибка."""
        text = """@APPLY abcdef1234567890
@APPEND SKIP
новая строка
@END"""
        with raises(DeckSyntaxError):
            parse_deck(text)


class TestValidateReplaceRegex:
    """Тесты валидации REPLACE_REGEX."""

    def test_valid_replace_regex(self):
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1-5"),
            payload=["s/foo/bar/g"],
        )
        validate_operations([op], 10)  # OK

    def test_replace_regex_out_of_range(self):
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("15-20"),
            payload=["s/foo/bar/g"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 10)

    def test_replace_regex_invalid_range(self):
        op = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("10-5"),
            payload=["s/foo/bar/g"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 10)


class TestValidateAppend:
    """Тесты валидации APPEND."""

    def test_valid_append(self):
        op = Operation(
            name="APPEND",
            address=None,
            payload=["новая строка"],
        )
        validate_operations([op], 10)  # OK

    def test_append_with_address_raises(self):
        """APPEND с адресом — ошибка валидации."""
        op = Operation(
            name="APPEND",
            address=Address.parse("5"),
            payload=["новая строка"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 10)


class TestMultipleOperations:
    """Тесты смешанных операций."""

    def test_replace_regex_then_append(self):
        """REPLACE_REGEX затем APPEND."""
        lines = ["foo\n", "baz\n"]
        op1 = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1"),
            payload=["s/foo/bar/"],
        )
        op2 = Operation(
            name="APPEND",
            address=None,
            payload=["новая"],
        )
        result = apply_operation(lines, op1)
        result = apply_operation(result, op2)
        assert result == ["bar\n", "baz\n", "новая\n"]

    def test_append_then_replace_regex(self):
        """APPEND затем REPLACE_REGEX."""
        lines = ["foo\n"]
        op1 = Operation(
            name="APPEND",
            address=None,
            payload=["baz"],
        )
        op2 = Operation(
            name="REPLACE_REGEX",
            address=Address.parse("1-2"),
            payload=["s/foo/bar/"],
        )
        result = apply_operation(lines, op1)
        result = apply_operation(result, op2)
        assert result == ["bar\n", "baz\n"]

    def test_delete_then_append(self):
        """DELETE затем APPEND."""
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op1 = Operation(
            name="DELETE",
            address=Address.parse("2"),
            payload=[],
        )
        op2 = Operation(
            name="APPEND",
            address=None,
            payload=["новая"],
        )
        result = apply_operation(lines, op1)
        result = apply_operation(result, op2)
        assert result == ["строка 1\n", "строка 3\n", "новая\n"]
