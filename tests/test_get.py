"""Тесты команды GET."""

import os
import tempfile

import pytest

from deck_editor.cmd_get import cmd_get, get_lines


class TestGetLines:
    """Тесты get_lines (программный интерфейс)."""

    def test_get_range(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            rev, output, total = get_lines(path, "1-2")
            assert "REV:" in output
            assert "000001:строка 1" in output
            assert "000002:строка 2" in output
            assert total == 3
        finally:
            os.unlink(path)

    def test_get_single_line(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            rev, output, total = get_lines(path, "2")
            assert "000002:строка 2" in output
        finally:
            os.unlink(path)

    def test_get_to_end(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            rev, output, total = get_lines(path, "2-")
            assert "000002:строка 2" in output
            assert "000003:строка 3" in output
            assert "000001" not in output
        finally:
            os.unlink(path)

    def test_get_empty_line(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\n\nстрока 3\n")
            path = f.name

        try:
            rev, output, total = get_lines(path, "1-3")
            assert "000002e" in output
        finally:
            os.unlink(path)

    def test_get_out_of_range(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\n")
            path = f.name

        try:
            with pytest.raises(Exception):
                get_lines(path, "5")
        finally:
            os.unlink(path)

    def test_get_invalid_range(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\n")
            path = f.name

        try:
            with pytest.raises(Exception):
                get_lines(path, "5-3")
        finally:
            os.unlink(path)

    def test_get_rev_consistency(self):
        """REV должен быть одинаковым при повторном вызове."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello")
            path = f.name

        try:
            rev1, _, _ = get_lines(path, "1")
            rev2, _, _ = get_lines(path, "1")
            assert rev1 == rev2
        finally:
            os.unlink(path)

    def test_get_to_end_out_of_range(self):
        """Spec §15 приоритет 12: N- out-of-range бросает AddressError.

        Для адреса '5-' на файле из 3 строк GET должен вернуть ошибку,
        а не пустой результат.
        """
        from deck_editor.utils import AddressError

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            with pytest.raises(AddressError) as exc_info:
                get_lines(path, "5-")
            assert "address out of file range" in str(exc_info.value)
        finally:
            os.unlink(path)

    def test_get_to_end_exact_boundary(self):
        """N- на последней строке — допустимо."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            rev, output, total = get_lines(path, "3-")
            assert "000003:строка 3" in output
            assert total == 3
        finally:
            os.unlink(path)

    def test_get_to_end_beyond_file(self):
        """N- за пределами файла (10- на файле из 3 строк) — ошибка."""
        from deck_editor.utils import AddressError

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            with pytest.raises(AddressError) as exc_info:
                get_lines(path, "10-")
            assert "address out of file range" in str(exc_info.value)
        finally:
            os.unlink(path)
