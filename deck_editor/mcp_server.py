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
    name="rev",
    description=(
        "RETURN only the REV hash and line count of a file. "
        "Use this when you only need to refresh the <rev> (e.g. after an "
        "external change) or to learn the file size. Do NOT call this to read "
        "content — use get() for that. Returns 'REV: <hash>' and 'LINES: <n>'."
    ),
)
def rev(file: str, workspace: str = None) -> str:
    """Return only the REV hash and total line count of a file.

    Args:
        file: Path to file (relative to workspace root).
        workspace: Optional workspace root.

    Returns:
        'REV: <hash>' and 'LINES: <count>'.
    """
    from deck_editor.cmd_get import get_rev_and_count
    from deck_editor.utils import (AccessDeniedError, format_error, validate_path)

    root = workspace or WORKSPACE_ROOT

    try:
        file_path = validate_path(file, root)
        file_rev, total_lines = get_rev_and_count(file_path)
    except FileNotFoundError:
        return format_error(FileNotFoundError(f"file not found — {file}"),
                            hint="check that the path is correct and the file exists in the workspace.")
    except AccessDeniedError as exc:
        return format_error(exc, hint="the path is outside the working directory.")

    output_lines = [f"REV: {file_rev}", f"LINES: {total_lines}"]
    return "\n".join(output_lines)


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
        format_error,
        format_numbered,
        validate_path,
    )

    root = workspace or WORKSPACE_ROOT
    file_path = validate_path(file, root)
    lines = content.splitlines()

    try:
        if len(lines) > max_create_lines:
            raise ValueError(
                f"CREATE exceeds limit: {len(lines)} > {max_create_lines}",
                hint=(f"CREATE writes a whole file; the limit is {max_create_lines} lines. "
                      f"For targeted edits use APPLY with @REPLACE instead."))

        if content and not content.endswith("\n"):
            content += "\n"

        file_exists = os.path.isfile(file_path)

        if file_exists:
            if rev is None:
                raise VersionConflictError(
                    "file exists, <rev> required to overwrite",
                    hint="call get() first to read the current REV, then pass it to CREATE.")
            current_rev = compute_xxhash(file_path)
            if rev != current_rev:
                raise VersionConflictError(
                    "version conflict — file changed",
                    hint="the file changed since you read it. Call get() again for a fresh REV, then retry.")
        else:
            if rev is not None:
                raise VersionConflictError(
                    "<rev> must not be specified for new file",
                    hint="this is a new file — call CREATE without a REV.")
    except (VersionConflictError, ValueError) as exc:
        return format_error(exc)

    atomic_write(file_path, content)

    new_rev = compute_content_hash(content)
    output_lines = [f"REV: {new_rev}"]
    output_lines.extend([format_numbered(i + 1, line) for i, line in enumerate(lines)])

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
        format_error,
        validate_path,
    )

    root = workspace or WORKSPACE_ROOT
    file_path = validate_path(file, root)

    try:
        deck_obj = parse_deck(deck)
    except DeckSyntaxError as exc:
        return format_error(exc)

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured

    try:
        result = apply_impl(file_path, deck_obj, root)
    except (
        DeckSyntaxError,
        VersionConflictError,
        AddressError,
        DeckLimitError,
        AccessDeniedError,
    ) as exc:
        sys.stdout = old_stdout
        return format_error(exc)
    except Exception as exc:
        sys.stdout = old_stdout
        return format_error(exc, hint="internal error — this should not happen. Check the deck and retry.")
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
