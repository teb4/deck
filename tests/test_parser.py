"""Тесты парсера колод."""

import pytest
from pytest import raises

from deck_editor.parser import (
    Address,
    Deck,
    Operation,
    parse_deck,
)
from deck_editor.utils import DeckSyntaxError


class TestAddress:
    """Тесты Address."""

    def test_single_line(self):
        addr = Address.parse("5")
        assert addr.start == 5
        assert addr.end is None

    def test_range(self):
        addr = Address.parse("5-10")
        assert addr.start == 5
        assert addr.end == 10

    def test_range_to_end(self):
        addr = Address.parse("5-")
        assert addr.start == 5
        assert addr.end is None

    def test_invalid(self):
        with raises(DeckSyntaxError):
            Address.parse("abc")

    def test_str_single(self):
        addr = Address.parse("5")
        assert str(addr) == "5"

    def test_str_range(self):
        addr = Address.parse("5-10")
        assert str(addr) == "5-10"

    def test_str_to_end(self):
        addr = Address.parse("5-")
        assert str(addr) == "5-"

    def test_to_tuple_single(self):
        addr = Address.parse("5")
        assert addr.to_tuple() == (5, None)

    def test_to_tuple_range(self):
        addr = Address.parse("5-10")
        assert addr.to_tuple() == (5, 10)


class TestParseHeader:
    """Тесты парсинга заголовка."""

    def test_dry_at(self):
        deck, end = self._parse_header("@DRY abcdef1234567890")
        assert deck.mode == "DRY"
        assert deck.rev == "abcdef1234567890"

        assert deck.marker == "@"

        deck, end = self._parse_header("$DRY abcdef1234567890")
        assert deck.mode == "DRY"
        assert deck.rev == "abcdef1234567890"

        deck, end = self._parse_header('@DRY_ALL abcdef1234567890')
        assert deck.mode == 'DRY_ALL'
        assert deck.rev == 'abcdef1234567890'
        deck, end = self._parse_header("@DRY_ALL abcdef1234567890")
        assert deck.mode == "DRY_ALL"
        assert deck.rev == "abcdef1234567890"

        assert deck.mode == "DRY_ALL"
        deck, end = self._parse_header("@APPLY abcdef1234567890")
        assert deck.mode == "APPLY"
        assert deck.rev == "abcdef1234567890"

        deck, end = self._parse_header('@APPLY abcdef1234567890')
        assert deck.mode == "APPLY"
    def test_apply_no_rev(self):
        with raises(DeckSyntaxError):
            self._parse_header('@APPLY')
    def test_invalid_header(self):
        with raises(DeckSyntaxError):
            self._parse_header("@INVALID abc123")

            self._parse_header('@INVALID abcdef1234567890')
        with raises(DeckSyntaxError):
            self._parse_header("")

    def _parse_header(self, line):
        from deck_editor.parser import _parse_header
        return _parse_header(line)


class TestParseDeck:
    """Тесты полного парсинга колоды."""

    def test_simple_replace(self):
        text = """@APPLY abcdef1234567890
@REPLACE 5
новая строка
@END"""
        deck = parse_deck(text)
        assert deck.mode == "APPLY"
        assert deck.rev == "abcdef1234567890"
        assert len(deck.operations) == 1
        assert deck.operations[0].name == "REPLACE"
        assert deck.operations[0].address.start == 5
        assert deck.operations[0].payload == ["новая строка"]

    def test_replace_range(self):
        text = """@APPLY abcdef1234567890
@REPLACE 10-12
новая 10
новая 11
новая 12
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].address.start == 10
        assert deck.operations[0].address.end == 12
        assert len(deck.operations[0].payload) == 3

    def test_delete(self):
        text = """@APPLY abcdef1234567890
@DELETE 15-20
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "DELETE"
        assert deck.operations[0].payload == []

    def test_insert(self):
        text = """@APPLY abcdef1234567890
@INSERT 5
строка 1
строка 2
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "INSERT"
        assert deck.operations[0].address.start == 5
        assert deck.operations[0].payload == ["строка 1", "строка 2"]

    def test_insert_head(self):
        text = """@APPLY abcdef1234567890
@INSERT_HEAD
новая строка
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "INSERT_HEAD"
        assert deck.operations[0].address is None
        assert deck.operations[0].payload == ["новая строка"]
    def test_insert_head_skip_with_at(self):
        """INSERT_HEAD + SKIP + payload с @ на нулевой колонке.

        Парсер должен распознать SKIP-флаг и считать весь текст до терминатора
        как payload, не пытаясь распознать @app.route как команду Deck.
        """
        text = """@APPLY abcdef1234567890
@INSERT_HEAD SKIP
@app.route("/test")
def handler():
    pass
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].name == "INSERT_HEAD"
        assert deck.operations[0].skip is True
        assert deck.operations[0].address is None
        assert "@app.route" in deck.operations[0].payload[0]

    def test_multiple_operations(self):
        text = """@APPLY abcdef1234567890
@DELETE 15-20
@REPLACE 5
новая пятая
@END"""
        deck = parse_deck(text)
        assert len(deck.operations) == 2
        assert deck.operations[0].name == "DELETE"
        assert deck.operations[1].name == "REPLACE"

    def test_dollar_marker(self):
        text = """$APPLY abcdef1234567890
$REPLACE 5
новая строка
$END"""
        deck = parse_deck(text)
        assert deck.marker == "$"

    def test_skip_modifier(self):
        text = """@APPLY abcdef1234567890
@REPLACE 5 SKIP
@REPLACE 10
@END"""
        deck = parse_deck(text)
        assert deck.operations[0].skip is True
        assert deck.operations[0].payload == ["@REPLACE 10"]

    def test_empty_deck(self):
        with raises(DeckSyntaxError):
            parse_deck("")

    def test_no_end(self):
        with raises(DeckSyntaxError):
            parse_deck('@APPLY abcdef1234567890\n@REPLACE 5\nновая\n')

    def test_wrong_terminator(self):
        with raises(DeckSyntaxError):
            parse_deck('@APPLY abcdef1234567890\n@REPLACE 5\nновая\n$END')

    def test_dollar_skip(self):
        text = """$APPLY abcdef1234567890
$REPLACE 5 SKIP
$REPLACE 10
$END"""
        deck = parse_deck(text)
        assert deck.marker == "$"
        assert deck.operations[0].skip is True
        assert deck.operations[0].payload == ["$REPLACE 10"]

    def test_trailing_lines_after_end(self):
        """Колода с линиями после терминатора должна вызвать ошибку."""
        deck_text = """@APPLY abcdef1234567890
@REPLACE 5
новая строка
@END
}
ещё одна строка
@END
"""
        with raises(DeckSyntaxError) as exc_info:
            parse_deck(deck_text)
        assert exc_info.value.args[0] == "trailing lines after END"
