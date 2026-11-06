"""Тесты подсказок (HINT) к ошибкам.

Deck предназначен для LLM, поэтому вместе с `ERROR: …` должна выводиться
подсказка `HINT: …`, описывающая, как должно быть правильно. Подсказка
должна использовать тот маркер (`@` или `$`), который действует в колоде.
"""

import subprocess

import pytest

from deck_editor.parser import parse_deck
from deck_editor.utils import (
    DeckSyntaxError,
    format_error,
    VersionConflictError,
    AddressError,
)


def _run_cli(args, stdin_data):
    return subprocess.run(
        [".venv/bin/python", "-m", "deck_editor"] + args,
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestFormatError:
    def test_without_hint(self):
        assert format_error(DeckSyntaxError("boom")) == "ERROR: boom"

    def test_with_hint_attribute(self):
        err = DeckSyntaxError("boom", hint="do this instead")
        assert format_error(err) == "ERROR: boom\nHINT: do this instead"

    def test_hint_param_overrides_attribute(self):
        err = DeckSyntaxError("boom", hint="old")
        assert format_error(err, hint="new") == "ERROR: boom\nHINT: new"

    def test_error_and_hint_on_separate_lines(self):
        err = DeckSyntaxError("boom", hint="hint text")
        out = format_error(err)
        assert out.split("\n") == ["ERROR: boom", "HINT: hint text"]


class TestSyntaxHints:
    def test_bad_address_hint(self):
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("@APPLY abcdef1234567890\n@REPLACE 5_10\nx\n@END")
        assert "invalid address: 5_10" in str(exc.value)
        assert exc.value.hint and "N-M" in exc.value.hint

    def test_missing_terminator_hint(self):
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("@APPLY abcdef1234567890\n@REPLACE 1\nx\n")
        assert "deck not terminated by END" in str(exc.value)
        assert "@END" in exc.value.hint

    def test_wrong_terminator_marker_hint_uses_header_marker(self):
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("@APPLY abcdef1234567890\n@REPLACE 1\nx\n$END")
        assert "terminator does not match deck marker" in str(exc.value)
        # маркер заголовка @ → и терминатор должен быть @END
        assert "@END" in exc.value.hint
        assert "$END" not in exc.value.hint

    def test_unknown_operation_hint(self):
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("@APPLY abcdef1234567890\n@REPLACE_CHAR 1\nx\n@END")
        assert "unknown operation: REPLACE_CHAR" in str(exc.value)
        assert "REPLACE" in exc.value.hint

    def test_extra_token_after_address_is_error(self):
        """Лишний токен после адреса — ошибка, а не payload."""
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("@APPLY abcdef1234567890\n@REPLACE 1-2 oops\nx\n@END")
        assert "unexpected token" in str(exc.value)

    def test_skip_with_args_is_error(self):
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("@APPLY abcdef1234567890\n@REPLACE 5 SKIP 3\nx\n@END")
        assert "SKIP takes no arguments" in str(exc.value)


class TestDollarMarkerHints:
    """Подсказки должны использовать действующий маркер ($)."""

    def test_dollar_bad_address_hint(self):
        """Подсказка к адресу маркер-независима (формат N-M общий для @ и $)."""
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("$APPLY abcdef1234567890\n$REPLACE bad\nx\n$END")
        assert "invalid address: bad" in str(exc.value)
        assert "N-M" in exc.value.hint

    def test_dollar_terminator_hint_uses_dollar(self):
        """Подсказка к терминатору использует действующий маркер $."""
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("$APPLY abcdef1234567890\n$REPLACE 1\nx\n@END")
        assert "terminator does not match deck marker" in str(exc.value)
        assert "$END" in exc.value.hint
        assert "@END" not in exc.value.hint

    def test_dollar_missing_terminator_hint(self):
        with pytest.raises(DeckSyntaxError) as exc:
            parse_deck("$APPLY abcdef1234567890\n$REPLACE 1\nx\n")
        assert "$END" in exc.value.hint


class TestRuntimeHints:
    def test_version_conflict_hint(self):
        err = VersionConflictError(
            "version conflict — file changed",
            hint="the file changed since you read it. Call deck_get again to get a fresh REV, then retry.")
        assert err.hint and "deck_get" in err.hint

    def test_address_out_of_range_hint(self):
        err = AddressError("address out of file range (lines: 1-3)",
                           hint="line 9 is outside the file")
        assert "line 9" in format_error(err)


class TestCLIOutputHints:
    """В CLI ошибка с подсказкой падает в stderr без traceback."""

    def _write(self, content):
        import tempfile, os
        fd, path = tempfile.mkstemp(dir="tests")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        return path

    def test_cli_error_has_hint(self):
        import xxhash
        path = self._write("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = xxhash.xxh64(open(path, "rb").read()).hexdigest()
            deck = f"@APPLY {rev}\n@REPLACE 5_10\nx\n@END"
            res = _run_cli(["apply", path, "-"], stdin_data=deck)
            assert res.returncode == 1
            assert "ERROR: invalid address: 5_10" in res.stderr
            assert "HINT:" in res.stderr
            assert "Traceback" not in res.stderr
        finally:
            import os
            os.unlink(path)
