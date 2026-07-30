"""Тесты CLI-ошибок: валидация колоды и адресов."""

import subprocess
import tempfile
import os

import pytest
import xxhash


def _run_cli(args: list[str], stdin_data: str | None = None) -> subprocess.CompletedProcess[str]:
    """Запускает deck-editor CLI и возвращает CompletedProcess."""
    cmd = [".venv/bin/python", "-m", "deck_editor"] + args
    return subprocess.run(
        cmd,
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _get_file_rev(path: str) -> str:
    """Вычисляет REV файла через xxhash."""
    h = xxhash.xxh64()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _write_file(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)


class TestCLIValidateErrors:
    """Тесты что validate_operations выбрасывает правильные исключения."""

    def test_replace_no_address(self):
        """@REPLACE без адреса → DeckSyntaxError."""
        from deck_editor.operations import validate_operations
        from deck_editor.parser import Operation

        op = Operation(name="REPLACE", address=None, payload=["новая\n"])
        with pytest.raises(Exception) as exc_info:
            validate_operations([op], 10)
        assert "REPLACE requires an address" in str(exc_info.value)

    def test_delete_with_payload(self):
        """@DELETE с payload → DeckSyntaxError."""
        from deck_editor.operations import validate_operations
        from deck_editor.parser import Operation, Address

        op = Operation(name="DELETE", address=Address.parse("5"), payload=["payload\n"])
        with pytest.raises(Exception) as exc_info:
            validate_operations([op], 10)
        assert "unexpected payload after DELETE" in str(exc_info.value)

    def test_invalid_address_range(self):
        """@REPLACE 10-5 → AddressError."""
        from deck_editor.operations import validate_operations
        from deck_editor.parser import Operation, Address

        op = Operation(name="REPLACE", address=Address.parse("10-5"), payload=["новая\n"])
        with pytest.raises(Exception) as exc_info:
            validate_operations([op], 10)
        assert "invalid address range — start > end" in str(exc_info.value)

    def test_insert_with_range(self):
        """@INSERT 5-10 → AddressError."""
        from deck_editor.operations import validate_operations
        from deck_editor.parser import Operation, Address

        op = Operation(name="INSERT", address=Address.parse("5-10"), payload=["новая\n"])
        with pytest.raises(Exception) as exc_info:
            validate_operations([op], 10)
        assert "INSERT requires single line address" in str(exc_info.value)

    def test_address_out_of_range(self):
        """@REPLACE 9999 на файле 61 строка → AddressError."""
        from deck_editor.operations import validate_operations
        from deck_editor.parser import Operation, Address

        op = Operation(name="REPLACE", address=Address.parse("9999"), payload=["новая\n"])
        with pytest.raises(Exception) as exc_info:
            validate_operations([op], 61)
        assert "address out of file range (lines: 1-61)" in str(exc_info.value)


class TestCLIOutput:
    """Тесты что CLI выводит ERROR: в stderr без traceback."""

    def _make_temp_file(self, content: str) -> str:
        """Создаёт временный файл внутри проекта и возвращает путь."""
        import uuid
        filename = f"tmp_cli_{uuid.uuid4().hex[:8]}.txt"
        path = os.path.join("tests", filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _cleanup(self, path: str) -> None:
        if os.path.exists(path):
            os.unlink(path)

    def test_replace_no_address_cli(self):
        """@REPLACE без адреса → ERROR: в stderr, без traceback."""
        path = self._make_temp_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = _get_file_rev(path)
            deck = f"@APPLY {rev}\n@REPLACE\nновая\n@END"
            result = _run_cli(["apply", path, "-"], stdin_data=deck)
            assert result.returncode == 1
            assert "ERROR: REPLACE requires an address" in result.stderr
            assert "Traceback" not in result.stderr
        finally:
            self._cleanup(path)

    def test_delete_with_payload_cli(self):
        """@DELETE с payload → ERROR: в stderr, без traceback."""
        path = self._make_temp_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = _get_file_rev(path)
            deck = f"@APPLY {rev}\n@DELETE 5\npayload\n@END"
            result = _run_cli(["apply", path, "-"], stdin_data=deck)
            assert result.returncode == 1
            assert "ERROR: unexpected payload after DELETE" in result.stderr
            assert "Traceback" not in result.stderr
        finally:
            self._cleanup(path)

    def test_invalid_address_range_cli(self):
        """@REPLACE 10-5 → ERROR: в stderr, без traceback."""
        path = self._make_temp_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = _get_file_rev(path)
            deck = f"@APPLY {rev}\n@REPLACE 10-5\nновая\n@END"
            result = _run_cli(["apply", path, "-"], stdin_data=deck)
            assert result.returncode == 1
            assert "ERROR: invalid address range — start > end" in result.stderr
            assert "Traceback" not in result.stderr
        finally:
            self._cleanup(path)

    def test_insert_with_range_cli(self):
        """@INSERT 5-10 → ERROR: в stderr, без traceback."""
        path = self._make_temp_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = _get_file_rev(path)
            deck = f"@APPLY {rev}\n@INSERT 5-10\nновая\n@END"
            result = _run_cli(["apply", path, "-"], stdin_data=deck)
            assert result.returncode == 1
            assert "ERROR: INSERT requires single line address" in result.stderr
            assert "Traceback" not in result.stderr
        finally:
            self._cleanup(path)

    def test_address_out_of_range_cli(self):
        """@REPLACE 9999 → ERROR: в stderr, без traceback."""
        path = self._make_temp_file("строка 1\nстрока 2\nстрока 3\n")
        try:
            rev = _get_file_rev(path)
            deck = f"@APPLY {rev}\n@REPLACE 9999\nновая\n@END"
            result = _run_cli(["apply", path, "-"], stdin_data=deck)
            assert result.returncode == 1
            assert "address out of file range" in result.stderr
            assert "Traceback" not in result.stderr
        finally:
            self._cleanup(path)


class TestCLIAddressErrors:
    """Тесты что cmd_get тоже выбрасывает AddressError."""

    def test_get_invalid_range(self):
        """GET 10-5 → AddressError."""
        from deck_editor.cmd_get import cmd_get
        import pytest

        with pytest.raises(Exception) as exc_info:
            cmd_get("tests/test_file.txt", "10-5")
        assert "invalid address range — start > end" in str(exc_info.value)

    def test_get_out_of_range(self):
        """GET 9999 → AddressError."""
        from deck_editor.cmd_get import cmd_get
        import pytest

        with pytest.raises(Exception) as exc_info:
            cmd_get("tests/test_file.txt", "9999")
        assert "address out of file range" in str(exc_info.value)

    def test_get_negative_address(self):
        """GET -1 → DeckSyntaxError (невалидный адрес)."""
        from deck_editor.cmd_get import cmd_get
        from deck_editor.utils import DeckSyntaxError

        with pytest.raises(DeckSyntaxError):
            cmd_get("tests/test_file.txt", "-1")


class TestNoValueErrorLeaks:
    """Убедиться что ValueError не утекает из operations.py и cmd_get.py."""

    def test_no_valueerror_in_operations(self):
        """validate_operations не должен выбрасывать ValueError."""
        from deck_editor.operations import validate_operations
        from deck_editor.parser import Operation, Address
        from deck_editor.utils import AddressError, DeckSyntaxError

        # Все эти ошибки должны быть AddressError или DeckSyntaxError
        test_cases = [
            (Operation(name="REPLACE", address=None, payload=[]), "DeckSyntaxError"),
            (Operation(name="DELETE", address=Address.parse("5"), payload=["x\n"]), "DeckSyntaxError"),
            (Operation(name="REPLACE", address=Address.parse("10-5"), payload=[]), "AddressError"),
            (Operation(name="INSERT", address=Address.parse("5-10"), payload=[]), "AddressError"),
            (Operation(name="REPLACE", address=Address.parse("9999"), payload=[]), "AddressError"),
        ]

        for op, expected_type in test_cases:
            with pytest.raises((AddressError, DeckSyntaxError)) as exc_info:
                validate_operations([op], 10)
            # Убедимся что это НЕ ValueError
            assert type(exc_info.value).__name__ in (expected_type, )

    def test_no_valueerror_in_cmd_get(self):
        """cmd_get не должен выбрасывать ValueError."""
        from deck_editor.cmd_get import cmd_get
        from deck_editor.utils import AddressError
        import pytest

        with pytest.raises(AddressError):
            cmd_get("tests/test_file.txt", "10-5")
