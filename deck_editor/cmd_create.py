"""Команда CREATE — создание нового файла или полная замена существующего."""

import os
import sys

from deck_editor.config import max_create_lines
from deck_editor.utils import (
    VersionConflictError,
    atomic_write,
    compute_content_hash,
    compute_xxhash,
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
        raise ValueError(f"CREATE exceeds limit: {len(lines)} > {max_create_lines}")

    # Обеспечиваем завершающий перевод строки
    if content and not content.endswith("\n"):
        content += "\n"

    file_exists = os.path.isfile(file_path)

    if file_exists:
        # Файл существует — rev обязателен
        if rev is None:
            raise VersionConflictError("file exists, <rev> required to overwrite")
        # Проверяем rev
        current_rev = compute_xxhash(file_path)
        if rev != current_rev:
            raise VersionConflictError("version conflict — file changed")
    else:
        # Файл не существует — rev запрещён
        if rev is not None:
            raise VersionConflictError("<rev> must not be specified for new file")

    # Атомарная запись
    atomic_write(file_path, content)

    # Возвращаем нумерованный листинг
    new_rev = compute_content_hash(content)
    output_lines = [f"REV: {new_rev}"]
    for i, line in enumerate(lines):
        line_num = i + 1
        padded = f"{line_num:06d}"
        if line == "":
            output_lines.append(f"{padded}e")
        else:
            output_lines.append(f"{padded}:{line}")

    print("\n".join(output_lines))
