"""Тесты APPLY / DRY / DRY_ALL."""

import os
import tempfile

import pytest

from deck_editor.apply import apply
from deck_editor.parser import Address, Deck, Operation
from deck_editor.utils import VersionConflictError, DeckSyntaxError


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
                        address=Address.parse("4"),
                        payload=["замена 4\n"],
                    ),
                ],
            )
            apply(path, deck, os.path.dirname(path))

            with open(path, "r") as fh:
                content = fh.read()
            # Обе операции привязаны к ОРИГИНАЛЬНЫМ строкам:
            # DELETE 2 удаляет строку 2, REPLACE 4 меняет строку 4.
            # Номера строк НЕ сдвигаются между операциями.
            assert content == "строка 1\nстрока 3\nзамена 4\n"
        finally:
            os.unlink(path)

    def test_apply_independent_zero_width_and_width(self):
        """INSERT_HEAD и REPLACE привязаны к оригиналу, а не к результату."""
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
                        address=Address.parse("1"),
                        payload=["вставка\n"],
                    ),
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2"),
                        payload=["замена 2\n"],
                    ),
                ],
            )
            apply(path, deck, os.path.dirname(path))

            with open(path, "r") as fh:
                content = fh.read()
            # INSERT_HEAD вставляет перед строкой 1, REPLACE 2 (оригинал) меняет строку 2.
            assert content == "вставка\nстрока 1\nзамена 2\n"
        finally:
            os.unlink(path)

    def test_apply_overlapping_operations_error(self):
        """Две операции на одной строке оригинала — ошибка «operations overlap»."""
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
                    ),
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2"),
                        payload=["новая\n"],
                    ),
                ],
            )
            with pytest.raises(DeckSyntaxError):
                apply(path, deck, os.path.dirname(path))
            # Файл не изменён после ошибки.
            with open(path, "r") as fh:
                assert fh.read() == "строка 1\nстрока 2\nстрока 3\n"
        finally:
            os.unlink(path)

    def test_apply_overlapping_touch_error(self):
        """REPLACE 1-2 и REPLACE 2-3 касаются строки 2 — ошибка."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("a\nb\nc\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="REPLACE",
                        address=Address.parse("1-2"),
                        payload=["x\n"],
                    ),
                    Operation(
                        name="REPLACE",
                        address=Address.parse("2-3"),
                        payload=["y\n"],
                    ),
                ],
            )
            with pytest.raises(DeckSyntaxError):
                apply(path, deck, os.path.dirname(path))
        finally:
            os.unlink(path)

    def test_apply_zero_width_same_gap_ok(self):
        """Несколько вставок в одну «дырку» — разрешено, порядок по колоде."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("строка 1\n")
            path = f.name

        try:
            rev = self._get_rev(path)
            deck = Deck(
                mode="APPLY",
                rev=rev,
                operations=[
                    Operation(
                        name="INSERT_HEAD",
                        address=Address.parse("1"),
                        payload=["первая\n"],
                    ),
                    Operation(
                        name="INSERT_HEAD",
                        address=Address.parse("2"),
                        payload=["вторая\n"],
                    ),
                ],
            )
            apply(path, deck, os.path.dirname(path))

            with open(path, "r") as fh:
                content = fh.read()
            # Обе вставки в «дырку» перед строкой 1 (INSERT_HEAD всегда gap 0),
            # порядок как в колоде.
            assert content == "первая\nвторая\nстрока 1\n"
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
