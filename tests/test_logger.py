"""Тесты модуля логирования."""

import io
import sys
import tempfile
import pathlib

from deck_editor.logger import (
    enable,
    disable,
    is_enabled,
    log_get,
    log_apply_start,
    log_apply_end,
    log_replace,
    log_replace_regex,
    log_append,
)


class TestLoggerEnableDisable:
    """Тесты включения/выключения логирования."""

    def setup_method(self):
        """Сбрасываем состояние логгера перед каждым тестом."""
        disable()

    def test_default_disabled(self):
        """Логирование по умолчанию отключено."""
        disable()
        assert is_enabled() is False

    def test_enable(self):
        """Включение логирования."""
        disable()
        enable()
        assert is_enabled() is True

    def test_disable(self):
        """Выключение логирования."""
        enable()
        disable()
        assert is_enabled() is False

    def test_toggle_multiple_times(self):
        """Многократное включение/выключение."""
        enable()
        assert is_enabled() is True
        disable()
        assert is_enabled() is False
        enable()
        assert is_enabled() is True


class TestLogGet:
    """Тесты логгера GET."""

    def setup_method(self):
        disable()
        enable()

    def test_log_get_output(self, capsys):
        """Проверяет формат вывода log_get."""
        log_get("/path/to/file.txt", "1-10", 100, 500)
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split()
        assert parts[1] == "GET"
        assert parts[2] == "file=/path/to/file.txt"
        assert parts[3] == "addr=1-10"
        assert parts[4] == "lines=100"
        assert parts[5] == "chars=500"

    def test_log_get_disabled(self, capsys):
        """Логирование GET отключено — ничего не выводит."""
        disable()
        log_get("/path/to/file.txt", "1-10", 100, 500)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestLogApplyStart:
    """Тесты логгера APPLY."""

    def setup_method(self):
        disable()
        enable()

    def test_log_apply_start_output(self, capsys):
        """Проверяет формат вывода log_apply_start."""
        log_apply_start("/path/to/file.txt", "abc123def45678")
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split()
        assert parts[1] == "APPLY"
        assert parts[2] == "file=/path/to/file.txt"
        assert parts[3] == "rev=abc123def45678"

    def test_log_apply_start_disabled(self, capsys):
        """Логирование APPLY отключено — ничего не выводит."""
        disable()
        log_apply_start("/path/to/file.txt", "abc123def45678")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestLogApplyEnd:
    """Тесты логгера END."""

    def setup_method(self):
        disable()
        enable()

    def test_log_apply_end_success(self, capsys):
        """Проверяет формат END success."""
        log_apply_end(True)
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split()
        assert parts[1] == "END"
        assert parts[2] == "success"

    def test_log_apply_end_failure(self, capsys):
        """Проверяет формат END failure."""
        log_apply_end(False)
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split()
        assert parts[1] == "END"
        assert parts[2] == "failure"

    def test_log_apply_end_disabled(self, capsys):
        """Логирование END отключено — ничего не выводит."""
        disable()
        log_apply_end(True)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestLogReplace:
    """Тесты логгера REPLACE."""

    def setup_method(self):
        disable()
        enable()

    def test_log_replace_single_line(self, capsys):
        """REPLACE одной строки."""
        log_replace(5, None)
        captured = capsys.readouterr()
        parts = captured.out.strip().split()
        assert parts[1] == "REPLACE"
        assert parts[2] == "5"

    def test_log_replace_range(self, capsys):
        """REPLACE диапазона."""
        log_replace(10, 20)
        captured = capsys.readouterr()
        parts = captured.out.strip().split()
        assert parts[1] == "REPLACE"
        assert parts[2] == "10-20"

    def test_log_replace_disabled(self, capsys):
        """Логирование REPLACE отключено."""
        disable()
        log_replace(5, None)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestLogReplaceRegex:
    """Тесты логгера REPLACE_REGEX."""

    def setup_method(self):
        disable()
        enable()

    def test_log_replace_regex_output(self, capsys):
        """Проверяет формат вывода REPLACE_REGEX."""
        log_replace_regex(1, 5, "foo/bar/g")
        captured = capsys.readouterr()
        parts = captured.out.strip().split()
        assert parts[1] == "REPLACE_REGEX"
        assert parts[2] == "1-5"
        assert parts[3] == "s/foo/bar/g"

    def test_log_replace_regex_disabled(self, capsys):
        """Логирование REPLACE_REGEX отключено."""
        disable()
        log_replace_regex(1, 5, "foo/bar/g")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestLogAppend:
    """Тесты логгера APPEND."""

    def setup_method(self):
        disable()
        enable()

    def test_log_append_output(self, capsys):
        """Проверяет формат вывода APPEND."""
        log_append(42)
        captured = capsys.readouterr()
        parts = captured.out.strip().split()
        assert parts[1] == "APPEND"
        assert parts[2] == "42"

    def test_log_append_zero(self, capsys):
        """APPEND с нулём строк."""
        log_append(0)
        captured = capsys.readouterr()
        parts = captured.out.strip().split()
        assert parts[1] == "APPEND"
        assert parts[2] == "0"

    def test_log_append_disabled(self, capsys):
        """Логирование APPEND отключено."""
        disable()
        log_append(42)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestTimestampFormat:
    """Тесты формата временной метки."""

    def setup_method(self):
        disable()
        enable()

    def test_log_get_timestamp_format(self, capsys):
        """Проверяет, что временная метка в формате ISO-8601."""
        log_get("/path/to/file.txt", "1-1", 1, 10)
        captured = capsys.readouterr()
        line = captured.out.strip()
        # Формат: YYYY-MM-DDTHH:MM:SS
        ts = line.split()[0]
        assert "T" in ts
        assert len(ts.split("T")[0]) == 10  # YYYY-MM-DD
        assert len(ts.split("T")[1]) == 8   # HH:MM:SS
