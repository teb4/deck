"""Тесты операций колоды."""

import pytest

from deck_editor.operations import (
    apply_operation,
    validate_operations,
)
from deck_editor.parser import Address, Operation


class TestReplace:
    """Тесты REPLACE."""

    def test_replace_single(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("2"),
            payload=["новая строка\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая строка\n", "строка 3\n"]

    def test_replace_range(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n", "строка 4\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("2-3"),
            payload=["новая 2\n", "новая 3\n", "новая 3.5\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая 2\n", "новая 3\n", "новая 3.5\n", "строка 4\n"]

    def test_replace_expand(self):
        """REPLACE: 1 строка → 3 строки."""
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=["новая 1\n", "новая 2\n", "новая 3\n"],
        )
        result = apply_operation(lines, op)
        assert len(result) == 4
        assert result[0] == "новая 1\n"
        assert result[3] == "строка 2\n"

    def test_replace_shrink(self):
        """REPLACE: 3 строки → 1 строка."""
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("1-3"),
            payload=["новая\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая\n"]

    def test_replace_to_end(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("2-"),
            payload=["новая 2\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая 2\n"]

    def test_replace_no_payload(self):
        """REPLACE без payload — удаляет строку (M→0)."""
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("2"),
            payload=[],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "строка 3\n"]

    def test_replace_payload_without_newline(self):
        """REPLACE: payload без \n — добавляется автоматически."""
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=["новая строка"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая строка\n", "строка 2\n"]

    def test_replace_empty_file(self):
        """REPLACE на пустом файле — ошибка валидации."""
        lines: list[str] = []
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=["новая\n"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 0)

    def test_replace_to_end_on_short_file(self):
        """REPLACE 1- на файле из 1 строки — заменяет всю строку."""
        lines = ["старая\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("1-"),
            payload=["новая\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая\n"]

    def test_replace_to_end_all_lines(self):
        """REPLACE 1- заменяет весь файл."""
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("1-"),
            payload=["новая\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая\n"]

    def test_replace_preserves_trailing_newline(self):
        """REPLACE: если payload уже имеет \n — не дублируется."""
        lines = ["строка 1\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=["новая\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая\n"]

    def test_replace_multiple_payload_lines(self):
        """REPLACE: payload из нескольких строк."""
        lines = ["старая\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=["новая 1", "новая 2", "новая 3"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая 1\n", "новая 2\n", "новая 3\n"]


class TestDelete:
    """Тесты DELETE."""

    def test_delete_single(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="DELETE",
            address=Address.parse("2"),
            payload=[],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "строка 3\n"]

    def test_delete_range(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n", "строка 4\n"]
        op = Operation(
            name="DELETE",
            address=Address.parse("2-3"),
            payload=[],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "строка 4\n"]

    def test_delete_to_end(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="DELETE",
            address=Address.parse("2-"),
            payload=[],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n"]

    def test_delete_all(self):
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="DELETE",
            address=Address.parse("1-"),
            payload=[],
        )
        result = apply_operation(lines, op)
        assert result == []


class TestInsert:
    """Тесты INSERT."""

    def test_insert_after(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="INSERT",
            address=Address.parse("2"),
            payload=["новая 2a\n", "новая 2b\n"],
        )
        result = apply_operation(lines, op)
        assert result == [
            "строка 1\n",
            "строка 2\n",
            "новая 2a\n",
            "новая 2b\n",
            "строка 3\n",
        ]

    def test_insert_after_last(self):
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="INSERT",
            address=Address.parse("2"),
            payload=["новая 2a\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "строка 2\n", "новая 2a\n"]

    def test_insert_after_first(self):
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="INSERT",
            address=Address.parse("1"),
            payload=["новая 1a\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая 1a\n", "строка 2\n"]


class TestInsertHead:
    """Тесты INSERT_HEAD."""

    def test_insert_head(self):
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="INSERT_HEAD",
            address=None,
            payload=["новая 0\n", "новая 0.5\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая 0\n", "новая 0.5\n", "строка 1\n", "строка 2\n"]

    def test_insert_head_empty(self):
        lines = []
        op = Operation(
            name="INSERT_HEAD",
            address=None,
            payload=["новая 1\n"],
        )
        result = apply_operation(lines, op)
        assert result == ["новая 1\n"]


class TestValidate:
    """Тесты валидации операций."""

    def test_valid_replace(self):
        op = Operation(
            name="REPLACE",
            address=Address.parse("1-3"),
            payload=["новая\n"],
        )
        validate_operations([op], 10)  # OK

    def test_invalid_range(self):
        op = Operation(
            name="REPLACE",
            address=Address.parse("10-5"),
            payload=["новая\n"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 10)

    def test_out_of_range(self):
        op = Operation(
            name="REPLACE",
            address=Address.parse("15-20"),
            payload=["новая\n"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 10)

    def test_insert_with_range(self):
        op = Operation(
            name="INSERT",
            address=Address.parse("5-10"),
            payload=["новая\n"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 10)

    def test_insert_head_no_address(self):
        op = Operation(
            name="INSERT_HEAD",
            address=None,
            payload=["новая\n"],
        )
        validate_operations([op], 10)  # OK
