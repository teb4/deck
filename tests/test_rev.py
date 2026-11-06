"""Тесты вызова rev (REV + количество строк)."""

import os
import tempfile

import pytest

from deck_editor.cmd_get import get_rev_and_count
from deck_editor.utils import AccessDeniedError, compute_xxhash


def _write_file(directory: str, name: str, content: str) -> str:
    """Создаёт файл с содержимым и возвращает абсолютный путь."""
    file_path = os.path.join(directory, name)
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return os.path.abspath(file_path)


class TestGetRevAndCount:
    """Юнит-тесты функции get_rev_and_count."""

    def test_rev_and_count(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "f.txt", "a\nb\nc\n")
            rev, total = get_rev_and_count(file_path)
            assert total == 3
            assert rev == compute_xxhash(file_path)

    def test_rev_matches_get(self):
        """REV из rev() должен совпадать с REV из get_lines()."""
        from deck_editor.cmd_get import get_lines

        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "f.txt", "x\ny\n")
            rev_from_get, _, _ = get_lines(file_path, "1-")
            rev_from_rev, _ = get_rev_and_count(file_path)
            assert rev_from_get == rev_from_rev

    def test_rev_consistency(self):
        """REV одинаков при повторном вызове на одном и том же файле."""
        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "f.txt", "hello\n")
            rev1, _ = get_rev_and_count(file_path)
            rev2, _ = get_rev_and_count(file_path)
            assert rev1 == rev2

    def test_rev_changes_after_edit(self):
        """REV меняется после изменения содержимого файла."""
        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "f.txt", "one\n")
            rev1, _ = get_rev_and_count(file_path)
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write("two\n")
            rev2, _ = get_rev_and_count(file_path)
            assert rev1 != rev2

    def test_rev_empty_file(self):
        """Пустой файл — REV и ноль строк."""
        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "empty.txt", "")
            rev, total = get_rev_and_count(file_path)
            assert total == 0
            assert rev == compute_xxhash(file_path)

    def test_rev_missing_file(self):
        """Отсутствие файла — FileNotFoundError."""
        with tempfile.TemporaryDirectory() as directory:
            missing = os.path.abspath(os.path.join(directory, "nope.txt"))
            with pytest.raises(FileNotFoundError):
                get_rev_and_count(missing)


class TestRevTool:
    """Тесты MCP-тулзы rev()."""

    def test_rev_tool_response(self):
        from deck_editor.mcp_server import rev

        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "f.txt", "a\nb\nc\nd\ne\n")
            output = rev(file=file_path, workspace=directory)
        lines = output.split("\n")
        assert lines[0].startswith("REV: ")
        assert lines[1] == "LINES: 5"

    def test_rev_tool_empty_file(self):
        from deck_editor.mcp_server import rev

        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "empty.txt", "")
            output = rev(file=file_path, workspace=directory)
        lines = output.split("\n")
        assert lines[0].startswith("REV: ")
        assert lines[1] == "LINES: 0"

    def test_rev_tool_missing_file(self):
        from deck_editor.mcp_server import rev

        with tempfile.TemporaryDirectory() as directory:
            missing = os.path.abspath(os.path.join(directory, "nope.txt"))
            output = rev(file=missing, workspace=directory)
        assert output.startswith("ERROR: file not found")

    def test_rev_tool_access_denied(self):
        from deck_editor.mcp_server import rev

        with tempfile.TemporaryDirectory() as directory:
            outside = _write_file(os.path.dirname(directory), "outside.txt", "x\n")
            output = rev(file=outside, workspace=directory)
        assert output.startswith("ERROR: ")
