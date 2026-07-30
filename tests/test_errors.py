"""Тесты ошибок."""

import os
import tempfile

import pytest

from deck_editor.parser import parse_deck
from deck_editor.utils import (
    AccessDeniedError,
    DeckLimitError,
    DeckSyntaxError,
    AddressError,
    VersionConflictError,
    validate_path,
)


class TestDeckSyntaxErrors:
    """Тесты ошибок синтаксиса колоды."""

    def test_empty_deck(self):
        with pytest.raises(DeckSyntaxError):
            parse_deck("")

    def test_no_header(self):
        with pytest.raises(DeckSyntaxError):
            parse_deck("@REPLACE 5\nновая\n@END")

    def test_no_end(self):
        with pytest.raises(DeckSyntaxError):
            parse_deck("@APPLY abc123\n@REPLACE 5\nновая")

    def test_wrong_terminator(self):
        with pytest.raises(DeckSyntaxError):
            parse_deck("@APPLY abc123\n@REPLACE 5\nновая\n$END")

    def test_invalid_address_range(self):
        with pytest.raises(DeckSyntaxError):
            parse_deck(
                "@APPLY abc123\n"
                "@REPLACE 10-5\n"
                "новая\n"
                "@END"
            )

    def test_insert_with_range(self):
        with pytest.raises(DeckSyntaxError):
            parse_deck(
                "@APPLY abc123\n"
                "@INSERT 5-10\n"
                "новая\n"
                "@END"
            )

    def test_insert_head_with_address(self):
        with pytest.raises(DeckSyntaxError):
            parse_deck(
                "@APPLY abc123\n"
                "@INSERT_HEAD 5\n"
                "новая\n"
                "@END"
            )

    def test_delete_with_payload(self):
        """DELETE не должен иметь payload — ошибка на этапе парсинга."""
        with pytest.raises(DeckSyntaxError) as exc_info:
            parse_deck(
                "@APPLY abcdef1234567890\n"
                "@DELETE 5\n"
                "payload\n"
                "@END"
            )
        assert "unexpected payload after DELETE" in str(exc_info.value)



class TestAccessDenied:
    """Тесты AccessDeniedError."""

    def test_outside_workspace(self, tmp_path):
        with pytest.raises(AccessDeniedError):
            validate_path("/tmp/outside/file.txt", str(tmp_path))

    def test_valid_nested(self, tmp_path):
        path = validate_path(str(tmp_path / "sub" / "file.txt"), str(tmp_path))
        assert "file.txt" in path


class TestVersionConflict:
    """Тесты VersionConflictError."""

    def test_error_message(self):
        err = VersionConflictError("version conflict — file changed")
        assert "version conflict" in str(err)


class TestDeckLimit:
    """Тесты DeckLimitError."""

    def test_error_message(self):
        err = DeckLimitError("deck size limit exceeded")
        assert "deck size limit" in str(err)


class TestAddressError:
    """Тесты AddressError."""

    def test_error_message(self):
        err = AddressError("address out of file range")
        assert "address" in str(err)
