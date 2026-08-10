"""MCP-сервер Deck Editor — экспортирует тулзы get, create, apply."""

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from deck_editor.logger import enable, disable
from deck_editor.config import log_enabled

app = FastMCP("deck-editor")

WORKSPACE_ROOT = os.environ.get("DECK_EDITOR_WORKSPACE", ".")

# Включаем логирование, если настроено в config
if log_enabled:
    enable()


@app.tool(
    name="get",
    description=(
        "READ file lines + REV hash. Call this ONCE, then call apply() immediately. "
        "Do NOT call get() multiple times. Do NOT read editor source code."
    ),
)
def get(file: str, addr: str, workspace: str = None) -> str:
    """Read lines from a file.

    Args:
        file: Path to file (relative to workspace root).
        addr: Address range (e.g. "1-50", "10", "5-").
        workspace: Optional workspace root.

    Returns:
        REV hash and numbered line listing.
    """
    from deck_editor.cmd_get import get_lines
    from deck_editor.utils import validate_path

    root = workspace or WORKSPACE_ROOT
    file_path = validate_path(file, root)
    rev, output, _ = get_lines(file_path, addr)
    return output


@app.tool(
    name="create",
    description=(
        "CREATE a NEW file or FULLY OVERWRITE an existing file. "
        "Use ONLY for new files or when >50% of lines change. "
        "For targeted edits use apply with @REPLACE instead. "
        "For overwriting existing file: rev from get() is REQUIRED. "
        "For new file: do NOT pass rev."
    ),
)
def create(file: str, content: str, rev: str | None = None, workspace: str = None) -> str:
    """Create a new file or overwrite an existing file.

    Args:
        file: Path to file (relative to workspace root).
        content: Content to write.
        rev: Current rev (required for overwriting existing files, forbidden for new files).
        workspace: Optional workspace root.

    Returns:
        New REV and numbered line listing.
    """
    from deck_editor.config import max_create_lines
    from deck_editor.utils import (
        VersionConflictError,
        atomic_write,
        compute_content_hash,
        compute_xxhash,
        validate_path,
    )

    root = workspace or WORKSPACE_ROOT
    file_path = validate_path(file, root)
    lines = content.splitlines()

    if len(lines) > max_create_lines:
        raise ValueError(f"CREATE exceeds limit: {len(lines)} > {max_create_lines}")

    if content and not content.endswith("\n"):
        content += "\n"

    file_exists = os.path.isfile(file_path)

    if file_exists:
        if rev is None:
            raise VersionConflictError("file exists, <rev> required to overwrite")
        current_rev = compute_xxhash(file_path)
        if rev != current_rev:
            raise VersionConflictError("version conflict — file changed. Call mcp__deck-editor__get(file, addr) FIRST to get current REV, then retry apply with that REV.")
    else:
        if rev is not None:
            raise VersionConflictError("<rev> must not be specified for new file")

    atomic_write(file_path, content)

    new_rev = compute_content_hash(content)
    output_lines = [f"REV: {new_rev}"]
    for i, line in enumerate(lines):
        line_num = i + 1
        padded = f"{line_num:06d}"
        if line == "":
            output_lines.append(f"{padded}e")
        else:
            output_lines.append(f"{padded}:{line}")

    return "\n".join(output_lines)


@app.tool(
    name="apply",
    description=(
        "EDIT a file. USE THIS INSTEAD OF write_file/sed/patch (they are BLOCKED). "
        "Call get() first, then call apply() immediately. Do NOT read editor source code. "
        "Deck format: @APPLY <rev>\n@REPLACE N-M\nnew text\n@END. "
        "@END must be last line. Payload has no line numbers."
    ),
)
def apply(file: str, deck: str, workspace: str = None) -> str:
    """Apply a deck to a file.

    Args:
        file: Path to file (relative to workspace root).
        deck: Deck text (e.g. "@APPLY abc123\\n@REPLACE 10\\nnew line\\n@END").
        workspace: Optional workspace root.

    Returns:
        Result of the apply operation.
    """
    import io

    from deck_editor.apply import apply as apply_impl
    from deck_editor.parser import parse_deck
    from deck_editor.utils import (
        AccessDeniedError,
        AddressError,
        DeckLimitError,
        DeckSyntaxError,
        VersionConflictError,
        validate_path,
    )

    root = workspace or WORKSPACE_ROOT
    file_path = validate_path(file, root)

    try:
        deck_obj = parse_deck(deck)
    except DeckSyntaxError as exc:
        return f"ERROR: {exc}"

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured

    try:
        result = apply_impl(file_path, deck_obj, root)
    except (VersionConflictError, AddressError, DeckLimitError, AccessDeniedError) as exc:
        sys.stdout = old_stdout
        return f"ERROR: {exc}"
    except Exception as exc:
        sys.stdout = old_stdout
        return f"ERROR: unexpected error — {exc}"
    finally:
        sys.stdout = old_stdout

    stdout_output = captured.getvalue().strip()

    if result is None:
        return stdout_output or "DRY: no changes"
    return f"{stdout_output}\n{result}" if stdout_output else result


def main() -> None:
    """Запуск MCP-сервера через stdio."""
    app.run()


if __name__ == "__main__":
    main()
