"""Тесты для повышения покрытия кода >90%.

Покрывают непокрытые ветки:
- apply.py: DRY_ALL с несколькими операциями, INSERT/INSERT_HEAD в сводке,
  обрезка diff (>50 строк), edge-кейсы
- cmd_get.py: edge-кейсы get_lines()
- cmd_create.py: пути валидации rev
- operations.py: edge-кейсы валидации
- utils.py: AccessDeniedError, DeckLimitError
"""

import os
import tempfile
from io import StringIO
import sys

import pytest

from deck_editor.apply import apply
from deck_editor.cmd_create import cmd_create
from deck_editor.cmd_get import get_lines
from deck_editor.operations import apply_operation, validate_operations
from deck_editor.parser import Address, Deck, Operation
from deck_editor.utils import (
    AccessDeniedError,
    DeckLimitError,
    compute_content_hash,
    compute_xxhash,
)


# ====================================================================
# apply.py — непокрытые ветки
# ====================================================================


class TestApplyCoverage:
    """Тесты для непокрытых веток apply.py."""

    def _write_file(self, content: str) -> str:
        """Создаёт временный файл с содержимым, возвращает путь."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def _rev(self, path: str) -> str:
        return compute_xxhash(path)

    def test_dry_all_multiple_operations(self):
        """DRY_ALL с несколькими операциями — проверяет строки 159+."""
        path = self._write_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="DRY_ALL",
                rev=rev,
                operations=[
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2"),
                        payload=["новая 2\n"],
                    ),
                    Operation(
                        name="INSERT",
                        address=Address.parse("1"),
                        payload=["новая 1a\n", "новая 1b\n"],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "REV:" in result
            assert "новая 2" in result
            assert "новая 1a" in result
            assert "новая 1b" in result
        finally:
            os.unlink(path)

    def test_dry_insert_summary(self):
        """DRY с INSERT — проверяет сводку INSERT."""
        path = self._write_file("строка 1\nстрока 2\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="DRY",
                rev=rev,
                operations=[
                    Operation(
                        name="INSERT",
                        address=Address.parse("1"),
                        payload=["новая 1a\n", "новая 1b\n"],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "INSERT after line 1" in result
            assert "2 lines inserted" in result
        finally:
            os.unlink(path)

    def test_dry_insert_head_summary(self):
        """DRY с INSERT_HEAD — проверяет сводку INSERT_HEAD."""
        path = self._write_file("строка 1\nстрока 2\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="DRY",
                rev=rev,
                operations=[
                    Operation(
                        name="INSERT_HEAD",
                        address=None,
                        payload=["новая 0\n"],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "INSERT_HEAD" in result
            assert "1 lines inserted" in result
        finally:
            os.unlink(path)

    def test_apply_insert_summary(self):
        """APPLY с INSERT — проверяет сводку INSERT."""
        path = self._write_file("строка 1\nстрока 2\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="INSERT",
                        address=Address.parse("1"),
                        payload=["новая 1a\n", "новая 1b\n"],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "APPLIED successfully" in result
            assert "INSERT after line 1" in result
            assert "2 lines inserted" in result
        finally:
            os.unlink(path)

    def test_apply_insert_head_summary(self):
        """APPLY с INSERT_HEAD — проверяет сводку INSERT_HEAD."""
        path = self._write_file("строка 1\nстрока 2\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="INSERT_HEAD",
                        address=None,
                        payload=["новая 0\n"],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "INSERT_HEAD" in result
            assert "1 lines inserted" in result
        finally:
            os.unlink(path)

    def test_diff_truncation(self):
        """Проверяет ветку обрезки diff (>50 строк, строки 108-111)."""
        lines = "\n".join(f"строка {i}" for i in range(1, 61)) + "\n"
        path = self._write_file(lines)
        try:
            rev = self._rev(path)
            new_payload = [f"новая {i}\n" for i in range(60)]
            deck = Deck(
                mode="DRY",
                rev=rev,
                operations=[
                    Operation(
                        name="REPLACE",
                        address=Address.parse("1"),
                        payload=new_payload,
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "... скрыто ..." in result
            assert result.count("строка") > 0
            assert result.count("новая") > 0
        finally:
            os.unlink(path)

    def test_apply_replace_to_end_summary(self):
        """APPLY REPLACE N- — проверяет сводку для is_to_end."""
        path = self._write_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2-"),
                        payload=["новая 2\n", "новая 3\n"],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "REPLACE lines 2-" in result
            assert "2 lines replaced with 2 lines" in result
        finally:
            os.unlink(path)

    def test_apply_delete_to_end_summary(self):
        """APPLY DELETE N- — проверяет сводку для is_to_end."""
        path = self._write_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="DELETE",
                        address=Address.parse("2-"),
                        payload=[],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "DELETE lines 2-" in result
            assert "2 lines deleted" in result
        finally:
            os.unlink(path)

    def test_dry_delete_to_end_summary(self):
        """DRY DELETE N- — проверяет сводку для is_to_end."""
        path = self._write_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = self._rev(path)
            deck = Deck(
                mode="DRY",
                rev=rev,
                operations=[
                    Operation(
                        name="DELETE",
                        address=Address.parse("2-"),
                        payload=[],
                    ),
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "DELETE lines 2-" in result
            assert "2 lines deleted" in result
        finally:
            os.unlink(path)


# ====================================================================
# cmd_get.py — непокрытые ветки get_lines()
# ====================================================================


class TestGetLinesCoverage:
    """Тесты для непокрытых веток cmd_get.py."""

    def _write_file(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def test_get_lines_single_line(self):
        """get_lines с адресом одной строки."""
        path = self._write_file("строка 1\nстрока 2\nстрока 3\n")
        rev, output, total = get_lines(path, "2")
        assert "REV:" in output
        assert "000002:строка 2" in output
        assert total == 3

    def test_get_lines_range(self):
        """get_lines с диапазоном."""
        path = self._write_file("строка 1\nстрока 2\nстрока 3\n")
        rev, output, total = get_lines(path, "1-2")
        assert "000001:строка 1" in output
        assert "000002:строка 2" in output
        assert "000003" not in output
        assert total == 3

    def test_get_lines_to_end(self):
        """get_lines с адресом N-."""
        path = self._write_file("строка 1\nстрока 2\nстрока 3\n")
        rev, output, total = get_lines(path, "2-")
        assert "000001" not in output
        assert "000002:строка 2" in output
        assert "000003:строка 3" in output
        assert total == 3

    def test_get_lines_empty_file(self):
        """get_lines на пустом файле."""
        path = self._write_file("")
        rev, output, total = get_lines(path, "1")
        assert output == f"REV: {rev}"
        assert total == 0

    def test_get_lines_out_of_range_start(self):
        """get_lines с start > len(lines)."""
        path = self._write_file("строка 1\n")
        with pytest.raises(Exception):
            get_lines(path, "5")

    def test_get_lines_out_of_range_negative(self):
        """get_lines с start < 1."""
        path = self._write_file("строка 1\n")
        with pytest.raises(Exception):
            get_lines(path, "0")

    def test_get_lines_empty_line_format(self):
        """get_lines с пустой строкой — суффикс 'e'."""
        path = self._write_file("строка 1\n\nстрока 3\n")
        rev, output, total = get_lines(path, "1-3")
        assert "000001:строка 1" in output
        assert "000002e" in output
        assert "000003:строка 3" in output


# ====================================================================
# cmd_create.py — непокрытые ветки валидации rev
# ====================================================================


class TestCreateCoverage:
    """Тесты для непокрытых веток cmd_create.py."""

    def _write_file(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def test_create_new_file_no_rev(self):
        """CREATE нового файла без rev."""
        path = self._write_file("")
        os.unlink(path)

        content = "новая строка\n"
        old_stdin = sys.stdin
        sys.stdin = StringIO(content)
        try:
            cmd_create(path, rev=None)
        finally:
            sys.stdin = old_stdin

        with open(path, "r") as fh:
            assert fh.read() == "новая строка\n"
        os.unlink(path)

    def test_create_existing_no_rev_error(self):
        """CREATE существующего файла без rev — ошибка."""
        path = self._write_file("существующий\n")
        try:
            content = "новая строка\n"
            old_stdin = sys.stdin
            sys.stdin = StringIO(content)
            with pytest.raises(Exception):
                cmd_create(path, rev=None)
        finally:
            sys.stdin = sys.__stdin__
            os.unlink(path)

    def test_create_new_with_rev_error(self):
        """CREATE нового файла с rev — ошибка."""
        path = self._write_file("")
        os.unlink(path)

        content = "новая строка\n"
        old_stdin = sys.stdin
        sys.stdin = StringIO(content)
        try:
            with pytest.raises(Exception):
                cmd_create(path, rev="abcdef1234567890")
        finally:
            sys.stdin = old_stdin
        if os.path.exists(path):
            os.unlink(path)


# ====================================================================
# operations.py — непокрытые ветки
# ====================================================================


class TestOperationsCoverage:
    """Тесты для непокрытых веток operations.py."""

    def test_validate_insert_head_no_address_ok(self):
        """INSERT_HEAD без адреса — валидация проходит."""
        op = Operation(
            name="INSERT_HEAD",
            address=None,
            payload=["новая\n"],
        )
        validate_operations([op], 10)  # OK

    def test_validate_insert_no_address_error(self):
        """INSERT без адреса — ошибка."""
        op = Operation(
            name="INSERT",
            address=None,
            payload=["новая\n"],
        )
        with pytest.raises(Exception):
            validate_operations([op], 10)

    def test_validate_replace_at_end(self):
        """REPLACE с адресом N- (is_to_end)."""
        op = Operation(
            name="REPLACE",
            address=Address.parse("2-"),
            payload=["новая\n"],
        )
        validate_operations([op], 10)  # OK

    def test_validate_delete_at_end(self):
        """DELETE с адресом N- (is_to_end)."""
        op = Operation(
            name="DELETE",
            address=Address.parse("2-"),
            payload=[],
        )
        validate_operations([op], 10)  # OK

    def test_validate_payload_limit(self):
        """Превышение лимита payload."""
        from deck_editor.config import max_deck_lines
        op = Operation(
            name="REPLACE",
            address=Address.parse("1"),
            payload=["строка\n"] * (max_deck_lines + 1),
        )
        with pytest.raises(DeckLimitError):
            validate_operations([op], 10)

    def test_apply_replace_single_no_newline(self):
        """REPLACE single line без \n в payload."""
        lines = ["строка 1\n", "строка 2\n", "строка 3\n"]
        op = Operation(
            name="REPLACE",
            address=Address.parse("2"),
            payload=["новая"],  # без \n
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая\n", "строка 3\n"]

    def test_apply_insert_no_newline(self):
        """INSERT без \n в payload."""
        lines = ["строка 1\n", "строка 2\n"]
        op = Operation(
            name="INSERT",
            address=Address.parse("1"),
            payload=["новая"],  # без \n
        )
        result = apply_operation(lines, op)
        assert result == ["строка 1\n", "новая\n", "строка 2\n"]


# ====================================================================
# utils.py — непокрытые ветки
# ====================================================================


class TestUtilsCoverage:
    """Тесты для непокрытых веток utils.py."""

    def test_validate_path_outside_workspace(self):
        """validate_path за пределами workspace — AccessDeniedError."""
        from deck_editor.utils import validate_path
        with pytest.raises(AccessDeniedError):
            validate_path("/etc/passwd", "/home/teb/me/projects/deck")

    def test_compute_content_hash(self):
        """compute_content_hash возвращает строку."""
        h = compute_content_hash("тест")
        assert len(h) == 16
        assert all(c in '0123456789abcdef' for c in h)

    def test_compute_xxhash(self):
        """compute_xxhash возвращает 16-символьный hex."""
        path = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        path.write("тест")
        path.flush()
        path.close()
        try:
            h = compute_xxhash(path.name)
            assert len(h) == 16
            assert all(c in '0123456789abcdef' for c in h)
        finally:
            os.unlink(path.name)
