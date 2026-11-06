"""Утилиты: xxhash, атомарная запись, валидация пути."""

import os
import stat
import tempfile
from typing import Optional

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


class DeckError(Exception):
    """Базовый класс ошибок Deck.

    Первый позиционный аргумент — само сообщение об ошибке ("что не так").
    `hint` — опциональная подсказка ("как должно быть правильно"),
    предназначенная для LLM. `str(err)` возвращает только сообщение,
    чтобы не ломать существующую обработку `str(exc)`.
    """

    def __init__(self, message, hint=None):
        super().__init__(message)
        self.hint = hint


class AccessDeniedError(DeckError):
    """Попытка выйти за пределы workspace."""

    pass


class VersionConflictError(DeckError):
    """REV не совпадает с текущим хэшем файла."""

    pass


class DeckSyntaxError(DeckError):
    """Ошибка синтаксиса колоды."""

    pass


class DeckLimitError(DeckError):
    """Превышен лимит размера колоды."""

    pass


class AddressError(DeckError):
    """Ошибка в адресации (диапазон, out of range)."""

    pass


# Невидимые символы, на которых LLM часто ошибается (см. суффикс 'i' в листинге).
# Список узкий: табуляция + «хитрые» неразрывные/zero-width/zero-space символы.
# Обычный пробел (0x20) и переносы строки НЕ учитываются — они не вводят LLM в заблуждение.
# (Для кодовых точек > U+FFFF используется \U с 8 цифрами; \U с 3-4 цифрами — ошибка.)
INVISIBLE_CHARS = frozenset(
    "\t"
    "\u00A0"   # nbsp — неразрывный пробел
    "\uFEFF"   # BOM / ZWNBSP (также zero-width no-break space)
    "\u200B"   # zero-width space
    "\u200C"   # zero-width non-joiner
    "\u200D"   # zero-width joiner
    "\u2060"   # word joiner
    "\u2061" "\u2062" "\u2063" "\u2064"   # скрытые операторы U+2061..U+2064
    "\U0000FFDE" "\U0000FFDF" "\U0000FFEA"   # скрытые символы U+FFDE..U+FFEA
)


def strip_eol(line: str) -> str:
    """Обрезает концевой перенос строки (\\n / \\r\\n), оставляя остальное содержимое."""
    return line.rstrip("\n").rstrip("\r\n")


def has_invisible(line: str) -> bool:
    """True, если строка содержит невидимые символы (табуляция, nbsp, zero-width и т.п.)."""
    return any(ch in INVISIBLE_CHARS for ch in line)


def line_suffix(content: str) -> str:
    """Определяет суффикс строки в нумерованном листинге.

    - 'e' — строка пустая (empty);
    - 'i' — строка содержит невидимые символы (invisible);
    - ''  — обычный текст.

    Приоритет: 'e' > 'i'. Аргумент `content` должен быть уже без переноса строки
    (см. strip_eol).
    """
    if content == "":
        return "e"
    if has_invisible(content):
        return "i"
    return ""


def format_numbered(line_num: int, raw_line: str) -> str:
    """Форматирует одну строку нумерованного листинга: NNNNNN:text / NNNNNNe / NNNNNNi."""
    padded = f"{line_num:06d}"
    content = strip_eol(raw_line)
    suffix = line_suffix(content)
    if suffix:
        return f"{padded}{suffix}"
    return f"{padded}:{content}"


def format_error(exc: BaseException, hint: Optional[str] = None) -> str:
    """Форматирует ошибку для вывода LLM: `ERROR: …` + опц. `HINT: …`.

    Подсказка берётся из атрибута `exc.hint`, если передан `hint` — переопределяет его.
    Обе строки вместе (разделены \n). В CLI это попадает в stderr,
    в MCP — в строку ответа. Подсказка выводится только если она задана.
    """
    msg = f"ERROR: {exc}"
    used_hint = hint if hint is not None else getattr(exc, "hint", None)
    if used_hint:
        msg += f"\nHINT: {used_hint}"
    return msg
