"""Тесты утилит."""

import os
import tempfile

import pytest

from deck_editor.utils import (
    compute_content_hash,
    compute_xxhash,
    validate_path,
)


class TestComputeXxhash:
    """Тесты вычисления xxhash."""

    def test_hash_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            f.flush()
            path = f.name

        try:
            h = compute_xxhash(path)
            assert isinstance(h, str)
            assert len(h) == 16  # xxh64 hex = 16 chars
        finally:
            os.unlink(path)

    def test_hash_same_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f1:
            f1.write("same content")
            f1.flush()
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f2:
            f2.write("same content")
            f2.flush()
            path2 = f2.name

        try:
            assert compute_xxhash(path1) == compute_xxhash(path2)
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_hash_different_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f1:
            f1.write("content a")
            f1.flush()
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f2:
            f2.write("content b")
            f2.flush()
            path2 = f2.name

        try:
            assert compute_xxhash(path1) != compute_xxhash(path2)
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestComputeContentHash:
    """Тесты вычисления xxhash от строки."""

    def test_hash_string(self):
        h = compute_content_hash("hello")
        assert isinstance(h, str)
        assert len(h) == 16

    def test_same_string(self):
        assert compute_content_hash("hello") == compute_content_hash("hello")

    def test_different_string(self):
        assert compute_content_hash("hello") != compute_content_hash("world")


class TestValidatePath:
    """Тесты валидации пути."""

    def test_valid_path(self, tmp_path):
        result = validate_path(str(tmp_path / "sub" / "file.txt"), str(tmp_path))
        assert result == str(tmp_path / "sub" / "file.txt")

    def test_outside_path(self, tmp_path):
        with pytest.raises(Exception):
            validate_path("/tmp/outside/file.txt", str(tmp_path))

    def test_nested_valid(self, tmp_path):
        deep = str(tmp_path / "a" / "b" / "c" / "file.txt")
        result = validate_path(deep, str(tmp_path))
        assert result == deep
