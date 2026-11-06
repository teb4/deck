"""Юнит-тесты для семантики «адреса относительно оригинала» (module anchored).

Проверяет:
  - `deck_editor.operations._check_overlaps` — пересечения/контакты областей;
  - `deck_editor.anchored.apply_anchored` — слияние операций с файлом.
"""

import pytest

from deck_editor.parser import Address, Operation
from deck_editor.operations import _check_overlaps
from deck_editor.anchored import apply_anchored
from deck_editor.utils import DeckSyntaxError


# ---------------------------------------------------------------------------
# _check_overlaps
# ---------------------------------------------------------------------------


class TestCheckOverlaps:
    """Проверка пересечений областей операций в оригинальном файле."""

    def test_no_overlap_disjoint_widths(self):
        ops = [
            Operation(name="REPLACE", address=Address.parse("1"), payload=["x\n"]),
            Operation(name="REPLACE", address=Address.parse("4"), payload=["y\n"]),
        ]
        _check_overlaps(ops, 5)  # OK

    def test_overlap_same_line(self):
        ops = [
            Operation(name="DELETE", address=Address.parse("2"), payload=[]),
            Operation(name="REPLACE", address=Address.parse("2"), payload=["x\n"]),
        ]
        with pytest.raises(DeckSyntaxError):
            _check_overlaps(ops, 5)

    def test_overlap_touching(self):
        ops = [
            Operation(name="REPLACE", address=Address.parse("1-2"), payload=["x\n"]),
            Operation(name="REPLACE", address=Address.parse("2-3"), payload=["y\n"]),
        ]
        with pytest.raises(DeckSyntaxError):
            _check_overlaps(ops, 3)

    def test_zero_width_same_gap_ok(self):
        ops = [
            Operation(name="INSERT_HEAD", address=Address.parse("1"), payload=["a\n"]),
            Operation(name="INSERT_HEAD", address=Address.parse("2"), payload=["b\n"]),
        ]
        _check_overlaps(ops, 3)  # обе в gap 0 — разрешено

    def test_zero_width_different_gap_conflict(self):
        ops = [
            Operation(name="INSERT_HEAD", address=Address.parse("1"), payload=["a\n"]),  # gap 0
            Operation(name="INSERT", address=Address.parse("1"), payload=["b\n"]),       # gap 1
        ]
        with pytest.raises(DeckSyntaxError):
            _check_overlaps(ops, 3)

    def test_zero_width_inside_width_conflict(self):
        ops = [
            Operation(name="REPLACE", address=Address.parse("1-3"), payload=["x\n"]),  # width [1,3]
            Operation(name="INSERT", address=Address.parse("2"), payload=["b\n"]),     # gap 2 inside
        ]
        with pytest.raises(DeckSyntaxError):
            _check_overlaps(ops, 3)

    def test_zero_width_at_width_end_boundary_conflict(self):
        ops = [
            Operation(name="REPLACE", address=Address.parse("1-2"), payload=["x\n"]),  # width [1,2]
            Operation(name="INSERT", address=Address.parse("2"), payload=["b\n"]),     # gap 2 == end
        ]
        with pytest.raises(DeckSyntaxError):
            _check_overlaps(ops, 2)


# ---------------------------------------------------------------------------
# apply_anchored
# ---------------------------------------------------------------------------


class TestApplyAnchored:
    """Слияние операций с оригинальным файлом."""

    def test_independent_width_ops(self):
        lines = ["строка 1\n", "строка 2\n", "строка 3\n", "строка 4\n"]
        ops = [
            Operation(name="DELETE", address=Address.parse("2"), payload=[]),
            Operation(name="REPLACE", address=Address.parse("4"), payload=["замена 4\n"]),
        ]
        result = apply_anchored(lines, ops, 4)
        assert result == ["строка 1\n", "строка 3\n", "замена 4\n"]

    def test_zero_width_before_width(self):
        lines = ["строка 1\n", "строка 2\n"]
        ops = [
            Operation(name="INSERT_HEAD", address=Address.parse("1"), payload=["вставка\n"]),
            Operation(name="REPLACE", address=Address.parse("2"), payload=["замена 2\n"]),
        ]
        result = apply_anchored(lines, ops, 2)
        assert result == ["вставка\n", "строка 1\n", "замена 2\n"]

    def test_zero_width_order_preserved(self):
        lines = ["строка 1\n"]
        ops = [
            Operation(name="INSERT_HEAD", address=Address.parse("1"), payload=["первая\n"]),
            Operation(name="INSERT_HEAD", address=Address.parse("2"), payload=["вторая\n"]),
        ]
        result = apply_anchored(lines, ops, 1)
        assert result == ["первая\n", "вторая\n", "строка 1\n"]

    def test_append_and_insert_head(self):
        lines = ["строка 1\n"]
        ops = [
            Operation(name="INSERT_HEAD", address=Address.parse("1"), payload=["в начало\n"]),
            Operation(name="APPEND", address=None, payload=["в конец\n"]),
        ]
        result = apply_anchored(lines, ops, 1)
        assert result == ["в начало\n", "строка 1\n", "в конец\n"]

    def test_regex_preserves_line_count(self):
        lines = ["foo\n", "foo\n", "baz\n"]
        ops = [
            Operation(name="REPLACE_REGEX", address=Address.parse("1-2"), payload=["s/foo/bar/g"]),
        ]
        result = apply_anchored(lines, ops, 3)
        assert result == ["bar\n", "bar\n", "baz\n"]

    def test_to_end_width(self):
        lines = ["a\n", "b\n", "c\n"]
        ops = [
            Operation(name="REPLACE", address=Address.parse("2-"), payload=["x\n", "y\n"]),
        ]
        result = apply_anchored(lines, ops, 3)
        assert result == ["a\n", "x\n", "y\n"]

    def test_insert_middle(self):
        lines = ["a\n", "c\n"]
        ops = [
            Operation(name="INSERT", address=Address.parse("1"), payload=["b\n"]),
        ]
        result = apply_anchored(lines, ops, 2)
        assert result == ["a\n", "b\n", "c\n"]

    def test_empty_file_append(self):
        lines = []
        ops = [
            Operation(name="APPEND", address=None, payload=["новая"]),
        ]
        result = apply_anchored(lines, ops, 0)
        assert result == ["новая\n"]
