"""Тесты команды CREATE."""

import os
import sys
import tempfile
from io import StringIO

import pytest

from deck_editor.cmd_create import cmd_create
from deck_editor.utils import VersionConflictError


class TestCreate:
    """Тесты CREATE."""

    def test_create_new_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        os.unlink(path)  # Удаляем, чтобы файл не существовал

        try:
            old_stdout = sys.stdout
            sys.stdout = StringIO()

            # Имитируем stdin
            import sys as _sys
            old_stdin = _sys.stdin
            _sys.stdin = StringIO("строка 1\nстрока 2\n")

            try:
                cmd_create(path, rev=None)
                output = sys.stdout.getvalue()
            finally:
                _sys.stdin = old_stdin
                sys.stdout = old_stdout

            assert os.path.isfile(path)
            with open(path, "r") as f:
                content = f.read()
            assert "строка 1" in content
            assert "строка 2" in content
            assert "REV:" in output
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_create_overwrite_with_rev(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("старый контент\n")
            path = f.name

        try:
            import xxhash
            h = xxhash.xxh64()
            with open(path, "rb") as f:
                h.update(f.read())
            rev = h.hexdigest()

            old_stdout = sys.stdout
            sys.stdout = StringIO()

            import sys as _sys
            old_stdin = _sys.stdin
            _sys.stdin = StringIO("новый контент\n")

            try:
                cmd_create(path, rev=rev)
                output = sys.stdout.getvalue()
            finally:
                _sys.stdin = old_stdin
                sys.stdout = old_stdout

            with open(path, "r") as f:
                content = f.read()
            assert "новый контент" in content
            assert "старый контент" not in content
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_create_overwrite_without_rev(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("старый контент\n")
            path = f.name

        try:
            import sys as _sys
            old_stdin = _sys.stdin
            _sys.stdin = StringIO("новый контент\n")

            try:
                with pytest.raises(VersionConflictError):
                    cmd_create(path, rev=None)
            finally:
                _sys.stdin = old_stdin
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_create_new_file_with_rev(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        os.unlink(path)

        try:
            import sys as _sys
            old_stdin = _sys.stdin
            _sys.stdin = StringIO("новый контент\n")

            try:
                with pytest.raises(VersionConflictError):
                    cmd_create(path, rev="abc123")
            finally:
                _sys.stdin = old_stdin
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_create_atomic(self):
        """CREATE должен атомарно записывать файл."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        os.unlink(path)

        try:
            import sys as _sys
            old_stdin = _sys.stdin
            _sys.stdin = StringIO("новый контент\n")

            try:
                cmd_create(path, rev=None)
            finally:
                _sys.stdin = old_stdin

            # Файл должен существовать и быть полным
            assert os.path.isfile(path)
            with open(path, "r") as f:
                content = f.read()
            assert content == "новый контент\n"
        finally:
            if os.path.exists(path):
                os.unlink(path)
