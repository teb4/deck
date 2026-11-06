"""Тесты суффикса 'i' (invisible) и унификации суффиксов в листинге.

Проверяет, что строки с невидимыми символами (табуляция, nbsp, zero-width и т.п.)
помечаются суффиксом 'i', пустые — 'e', а обычные строки — без суффикса.
А также что суффиксы 'e' и 'i' взаимно исключают друг друга.
"""

import os
import tempfile

import pytest

from deck_editor.cmd_get import cmd_get, get_lines
from deck_editor.utils import (
    format_numbered,
    has_invisible,
    line_suffix,
    strip_eol,
)


class TestUnit:
    """Юнит-тесты для utils.line_suffix / has_invisible / format_numbered."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", "e"),          # пустая
            ("\n", "e"),        # только перенос -> пустая
            ("\r\n", "e"),      # windows перенос -> пустая
            ("\t", "i"),        # табуляция
            ("a\tb", "i"),      # таб внутри
            ("a\u00A0b", "i"),  # nbsp
            ("a\uFEFFb", "i"),  # BOM / ZWNBSP
            ("a\u200Bb", "i"),  # zero-width space
            ("a\u2060b", "i"),  # word joiner
            ("plain", ""),      # обычный текст
            ("  spaced", ""),   # обычные пробелы -> без суффикса
            ("текст 1", ""),    # кириллица + обычный пробел
            ("tab\tend", "i"),
        ],
    )
    def test_line_suffix(self, raw, expected):
        assert line_suffix(strip_eol(raw)) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("\t", True),
            ("a\u00A0b", True),
            ("a\u200B", True),
            ("plain", False),
            ("  ", False),
            ("текст", False),
        ],
    )
    def test_has_invisible(self, raw, expected):
        assert has_invisible(raw) is expected

    def test_priority_e_over_i(self):
        # Пустая строка не может быть одновременно 'e' и 'i'.
        assert line_suffix("") == "e"
        assert line_suffix(strip_eol("\n")) == "e"

    @pytest.mark.parametrize(
        "num,raw,expected",
        [
            (1, "hello\n", "000001:hello"),
            (2, "\n", "000002e"),
            (3, "\tfoo\n", "000003i"),
            (4, "a\u00A0b\n", "000004i"),
            (123456, "x\n", "123456:x"),
        ],
    )
    def test_format_numbered(self, num, raw, expected):
        assert format_numbered(num, raw) == expected


class TestGetInvisibleSuffix:
    """Интеграционные тесты: GET помечает невидимые строки суффиксом 'i'."""

    def _write(self, content):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_get_marks_tab_line(self):
        path = self._write("строка 1\n\tтаблица\nстрока 3\n")
        try:
            rev, output, total = get_lines(path, "1-3")
            assert "000001:строка 1" in output
            assert "000002i" in output
            assert "000003:строка 3" in output
            assert total == 3
        finally:
            os.unlink(path)

    def test_get_marks_nbsp_line(self):
        path = self._write("a\u00A0b\n")
        try:
            _, output, _ = get_lines(path, "1")
            assert output.splitlines()[1] == "000001i"
        finally:
            os.unlink(path)

    def test_get_marks_zwsp_line(self):
        path = self._write("x\u200Bx\n")
        try:
            _, output, _ = get_lines(path, "1")
            assert output.splitlines()[1] == "000001i"
        finally:
            os.unlink(path)

    def test_get_plain_lines_no_suffix(self):
        path = self._write("строка 1\nстрока 2\n")
        try:
            _, output, _ = get_lines(path, "1-2")
            lines = output.splitlines()
            assert lines[1] == "000001:строка 1"
            assert lines[2] == "000002:строка 2"
        finally:
            os.unlink(path)

    def test_get_empty_line_suffix_e(self):
        path = self._write("строка 1\n\nстрока 3\n")
        try:
            _, output, _ = get_lines(path, "1-3")
            lines = output.splitlines()
            assert lines[1] == "000001:строка 1"
            assert lines[2] == "000002e"
            assert lines[3] == "000003:строка 3"
        finally:
            os.unlink(path)

    def test_cmd_get_marks_invisible(self):
        """cmd_get (CLI-путь) тоже помечает невидимые строки."""
        path = self._write("good\n\tbad\n")
        try:
            cmd_get(path, "1-2")
        finally:
            os.unlink(path)
