"""Тесты атомарной записи."""

import os
import tempfile

import pytest

from deck_editor.utils import atomic_write


class TestAtomicWrite:
    """Тесты atomic_write."""

    def test_write_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "new_file.txt")
            assert not os.path.exists(path)

            atomic_write(path, "hello\nworld\n")

            assert os.path.isfile(path)
            with open(path, "r") as f:
                content = f.read()
            assert content == "hello\nworld\n"

    def test_overwrite_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "file.txt")
            with open(path, "w") as f:
                f.write("old content\n")

            atomic_write(path, "new content\n")

            with open(path, "r") as f:
                content = f.read()
            assert content == "new content\n"

    def test_preserves_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "file.txt")
            with open(path, "w") as f:
                f.write("old\n")
            os.chmod(path, 0o640)

            atomic_write(path, "new\n")

            mode = os.stat(path).st_mode & 0o777
            assert mode == 0o640

    def test_atomic_on_error(self):
        """При ошибке файл должен остаться нетронутым."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "file.txt")
            with open(path, "w") as f:
                f.write("original content\n")

            # atomic_write с некорректным путём (несуществующая директория)
            bad_path = os.path.join(tmpdir, "nonexistent", "file.txt")
            with pytest.raises(OSError):
                atomic_write(bad_path, "bad content\n")

            # Оригинальный файл должен остаться
            with open(path, "r") as f:
                content = f.read()
            assert content == "original content\n"

    def test_content_integrity(self):
        """Проверка целостности контента после записи."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "file.txt")
            content = "line 1\nline 2\nline 3\n" * 100

            atomic_write(path, content)

            with open(path, "r") as f:
                read_back = f.read()
            assert read_back == content
