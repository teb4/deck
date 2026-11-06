"""Команда CREATE — создание нового файла или полная замена существующего."""

import os
import sys

from deck_editor.config import max_create_lines
from deck_editor.utils import (
    VersionConflictError,
    atomic_write,
    compute_content_hash,
    compute_xxhash,
    format_numbered,
)


def cmd_create(file_path: str, rev: str = None, workspace_root: str = None) -> None:
    """
    Читает stdin, создаёт или перезаписывает файл.

    Args:
        file_path: Путь к файлу.
        rev: Текущий rev (обязателен для перезаписи).
        workspace_root: Корневая директория workspace (для валидации пути).
    """
    from deck_editor.utils import validate_path

    if workspace_root is not None:
        file_path = validate_path(file_path, workspace_root)

    content = sys.stdin.read()
    lines = content.splitlines()

    if len(lines) > max_create_lines:
        raise ValueError(
            f"CREATE exceeds limit: {len(lines)} > {max_create_lines}",
            hint=(f"CREATE writes a whole file; the limit is {max_create_lines} lines. "
                  f"For targeted edits use APPLY with @REPLACE instead."))

    # Обеспечиваем завершающий перевод строки
    if content and not content.endswith("\n"):
        content += "\n"

    file_exists = os.path.isfile(file_path)

    if file_exists:
        # Файл существует — rev обязателен
        if rev is None:
            raise VersionConflictError(
                "file exists, <rev> required to overwrite",
                hint="call deck_get (or deck_rev) first to read the current REV, then pass it to CREATE.")
        # Проверяем rev
        current_rev = compute_xxhash(file_path)
        if rev != current_rev:
            raise VersionConflictError(
                "version conflict — file changed",
                hint="the file changed since you read it. Call deck_get again to get a fresh REV, then retry.")
    else:
        # Файл не существует — rev запрещён
        if rev is not None:
            raise VersionConflictError(
                "<rev> must not be specified for new file",
                hint="this is a new file — call CREATE without a REV.")

    # Атомарная запись
    atomic_write(file_path, content)

    # Возвращаем нумерованный листинг
    new_rev = compute_content_hash(content)
    output_lines = [f"REV: {new_rev}"]
    output_lines.extend([format_numbered(i + 1, line) for i, line in enumerate(lines)])

    print("\n".join(output_lines))
