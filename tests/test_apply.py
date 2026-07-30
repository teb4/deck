"""Тесты APPLY / DRY / DRY_ALL."""

import os
import tempfile

import pytest

from deck_editor.apply import apply
from deck_editor.parser import Address, Deck, Operation
from deck_editor.utils import VersionConflictError


class TestApply:
    """Тесты применения колоды."""

    def test_apply_replace(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2"),
                        payload=["новая строка\n"],
                    )
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "APPLIED successfully" in result

            with open(path, "r") as fh:
                content = fh.read()
            assert content == "строка 1\nновая строка\nстрока 3\n"
        finally:
            os.unlink(path)

    def test_apply_delete(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="DELETE",
                        address=Address.parse("2"),
                        payload=[],
                    )
                ],
            )
            apply(path, deck, os.path.dirname(path))

            with open(path, "r") as fh:
                content = fh.read()
            assert content == "строка 1\nстрока 3\n"
        finally:
            os.unlink(path)

    def test_apply_insert(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="INSERT",
                        address=Address.parse("1"),
                        payload=["новая 1a\n", "новая 1b\n"],
                    )
                ],
            )
            apply(path, deck, os.path.dirname(path))

            with open(path, "r") as fh:
                content = fh.read()
            assert content == "строка 1\nновая 1a\nновая 1b\nстрока 2\n"
        finally:
            os.unlink(path)

    def test_apply_insert_head(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="INSERT_HEAD",
                        address=None,
                        payload=["новая 0\n"],
                    )
                ],
            )
            apply(path, deck, os.path.dirname(path))

            with open(path, "r") as fh:
                content = fh.read()
            assert content == "новая 0\nстрока 1\nстрока 2\n"
        finally:
            os.unlink(path)

    def test_version_conflict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\n")
            path = f.name

        try:
            deck = Deck(
                mode="APPLY",
                rev="wrong_rev",
                operations=[],
            )
            with pytest.raises(VersionConflictError):
                apply(path, deck, os.path.dirname(path))
        finally:
            os.unlink(path)

    def test_apply_multiple_operations(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\nстрока 3\nстрока 4\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="DELETE",
                        address=Address.parse("2"),
                        payload=[],
                    ),
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2"),
                        payload=["новая 2\n", "новая 3\n"],
                    ),
                ],
            )
            apply(path, deck, os.path.dirname(path))

            with open(path, "r") as fh:
                content = fh.read()
            # После DELETE строка 2 удалена, строка 3 стала строкой 2
            # REPLACE 2 заменяет строку 2 (была строка 3) на 2 строки
            assert content == "строка 1\nновая 2\nновая 3\nстрока 4\n"
        finally:
            os.unlink(path)

    def test_dry_mode(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="DRY",
                rev=rev,
                operations=[
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2"),
                        payload=["новая строка\n"],
                    )
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert isinstance(result, str)  # DRY возвращает diff-строку

            with open(path, "r") as fh:
                content = fh.read()
            assert content == "строка 1\nстрока 2\n"  # Файл не изменён
        finally:
            os.unlink(path)

    def test_dry_all_mode(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\nстрока 2\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="DRY_ALL",
                rev=rev,
                operations=[
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2"),
                        payload=["новая строка\n"],
                    )
                ],
            )
            result = apply(path, deck, os.path.dirname(path))
            assert "REV:" in result
            assert "новая строка" in result

            with open(path, "r") as fh:
                content = fh.read()
            assert content == "строка 1\nстрока 2\n"  # DRY_ALL не меняет файл
        finally:
            os.unlink(path)
    def test_dry_all_empty_file(self):
        """Spec §10: DRY_ALL на абсолютно пустом файле возвращает (Empty file: 0 lines)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(mode="DRY_ALL", rev=rev, operations=[])
            result = apply(path, deck, os.path.dirname(path))
            assert "(Empty file: 0 lines)" in result
            assert "REV:" in result
        finally:
            os.unlink(path)

    def _get_rev(self, path):
        import xxhash
        h = xxhash.xxh64()
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
