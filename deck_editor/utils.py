"""Утилиты: xxhash, атомарная запись, валидация пути."""

import os
import stat
import tempfile

import xxhash

# Константы вынесены в deck_editor.config:
#   max_deck_lines, max_create_lines, diff_preview_lines


def compute_xxhash(file_path: str) -> str:
    """Вычисляет xxhash64 файла и возвращает hex-строку."""
    h = xxhash.xxh64()
    with open(file_path, "rb") as fh:
        while True:
            chunk = fh.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_content_hash(content: str) -> str:
    """Вычисляет xxhash64 от строкового содержимого."""
    return xxhash.xxh64(content).hexdigest()


def validate_path(file_path: str, workspace_root: str) -> str:
    """
    Проверяет, что file_path находится внутри workspace_root.
    Возвращает абсолютный путь.
    """
    # Разрешаем symlink до проверки пути
    file_path = os.path.realpath(file_path)
    abs_file = os.path.abspath(file_path)
    abs_root = os.path.abspath(workspace_root)
    if not abs_file.startswith(abs_root + os.sep) and abs_file != abs_root:
        raise AccessDeniedError("access denied — path outside working directory")
    return abs_file


def atomic_write(file_path: str, content: str) -> None:
    """
    Атомарная запись файла по протоколу safe-write:
    1. Разрешаем symlink
    2. Temp file в той же директории
    3. Write + fsync
    4. Сохранение метаданных (права доступа)
    5. Атомарная замена через os.replace()
    6. Откат при ошибке
    """
    # Разрешаем symlink до создания временного файла
    file_path = os.path.realpath(file_path)
    target_dir = os.path.dirname(file_path)
    fd, tmp_path = tempfile.mkstemp(dir=target_dir)
    try:
        try:
            # Считываем права оригинала, если файл существует
            try:
                original_mode = os.stat(file_path).st_mode
            except OSError:
                original_mode = None

            # Записываем данные
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            fd = None  # Уже закрыли

            # Применяем права оригинала
            if original_mode is not None:
                os.chmod(tmp_path, stat.S_IMODE(original_mode))

            # Атомарная замена
            os.replace(tmp_path, file_path)
        except BaseException:
            # Откат при ошибке
            if fd is not None:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except BaseException:
        raise


class AccessDeniedError(Exception):
    """Попытка выйти за пределы workspace."""

    pass


class VersionConflictError(Exception):
    """REV не совпадает с текущим хэшем файла."""

    pass


class DeckSyntaxError(Exception):
    """Ошибка синтаксиса колоды."""

    pass


class DeckLimitError(Exception):
    """Превышен лимит размера колоды."""

    pass


class AddressError(Exception):
    """Ошибка в адресации (диапазон, out of range)."""

    pass
