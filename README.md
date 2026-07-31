# Deck Editor

A transactional text editor designed specifically for LLM agents.
The model does not see or edit the file directly — it receives numbered fragments from the editor and responds with a batch ("deck") of commands, which is applied to the file atomically in a single pass.
To control integrity and protect against version races, xxhash (`xxh64`) is used. `REV` is a 16-character hex hash of the current file contents.

## Table of Contents
- [Installation](#installation)
- [CLI](#cli)
- [Reading lines (GET)](#reading-lines-get)
- [Creating a file (CREATE)](#creating-a-file-create)
- [Applying a deck (APPLY)](#applying-a-deck-apply)
- [Deck structure](#deck-structure)
- [Deck operations](#deck-operations)
- [Addressing](#addressing)
- [Markers `@` and `$`](#markers--and-)
- [`SKIP` modifier](#skip-modifier)
- [Versions, REV and version conflict](#versions-rev-and-version-conflict)
- [Limits](#limits)
- [Security and atomic writing](#security-and-atomic-writing)
- [MCP server](#mcp-server)
- [Recommended workflow for LLM agents](#recommended-workflow-for-llm-agents)
- [Errors](#errors)
- [Quick start](#quick-start)
- [Full specification](#full-specification)
- [Project structure](#project-structure)

## Installation
Requirements:
- Python 3.13+
- A virtual environment is recommended

Steps:
```bash
# 1. Clone the repository
git clone <repo-url>
cd deck

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install the package
pip install -e .

# 4. (Optional) Install MCP dependencies
pip install -e '.[mcp]'
```

After installation, the following are available:
| Command | Description |
| --- | --- |
| `deck-editor` | CLI for manual use |
| `deck-editor-mcp` | MCP server for Qwen Code and other MCP clients |

## CLI
Main commands:
```bash
deck-editor get <file> <addr>
deck-editor create <file> [<rev>]
deck-editor apply <file> -
```
In the examples below, the deck is passed via stdin. The `-` symbol means reading the deck from standard input.

### Reading lines (GET)
Command:
```bash
deck-editor get file.py 1-50
```
Response:
```text
REV: a3f5b7c9d1e2f405
000001:def foo():
000002:    pass
000003e
000004:def bar():
```
Format:
- `REV: <hash>` — 16-character xxh64 hash of the current file state.
- `NNNNNN:text` — non-empty line, minimum 6 digits.
- `NNNNNNe` — empty line, suffix `e`.

Line numbers appear only in `GET` and `CREATE` responses. There are no line numbers in the actual file on disk.

For an absolutely empty file, `GET` returns only `REV`:
```text
REV: a3f5b7c9d1e2f405
```

### Creating a file (CREATE)
`CREATE` is an external CLI command. It is not part of a deck.
`CREATE` reads the contents of a new file or a full replacement of an existing file from `stdin` until EOF.

#### Creating a new file
For a new file, `REV` must not be specified:
```bash
printf 'line one\nline two\n' | deck-editor create newfile.txt
```
Response:
```text
REV: a3f5b7c9d1e2f406
000001:line one
000002:line two
```

#### Overwriting an existing file
For overwriting an existing file, `REV` is mandatory:
```bash
printf 'new content\n' | deck-editor create existing.txt a3f5b7c9d1e2f405
```
Response:
```text
REV: a3f5b7c9d1e2f406
000001:new content
```

Rules:
- if the file does not exist, `REV` must not be specified;
- if the file exists, `REV` is mandatory;
- on a successful `CREATE`, the full numbered listing of the result is returned, including the new `REV`;
- the contents of `stdin` are not scanned as a deck;
- lines like `@END`, `@REPLACE`, `$END`, `$VAR` in `CREATE` are safe and treated as regular text.

Example error:
```bash
printf 'text\n' | deck-editor create newfile.txt a3f5b7c9d1e2f405
```
Expected error:
```text
ERROR: <rev> must not be specified for new file
```

### Applying a deck (APPLY)
A deck is intended to modify an existing file.
Applying a deck to a non-existent file is an error. Use `CREATE` to create a file.

A deck has three modes:
| Mode | Description | Disk write |
| --- | --- | --- |
| `@DRY` | preview in unified diff format | no |
| `@DRY_ALL` | preview of the full numbered listing | no |
| `@APPLY` | atomic application of changes | yes |

#### `@DRY` example
```bash
deck-editor apply file.py - <<'EOF'
@DRY a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Parameter and file processing
@END
EOF
```
Response:
```text
REV: a3f5b7c9d1e2f406 (would be new)
Original: a3f5b7c9d1e2f405 → Modified: a3f5b7c9d1e2f406
--- original
+++ modified
@@ -2,1 +2,1 @@
-    1.1 Parameter processing
+    1.1 Parameter and file processing
Operations applied:
- REPLACE lines 2-2 (1 line replaced with 1 line)
```
If the modified block is larger than 50 lines, the first 10 lines are shown, then `... hidden ...`, then the last 10 lines.

#### `@DRY_ALL` example
```bash
deck-editor apply file.py - <<'EOF'
@DRY_ALL a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Parameter and file processing
@END
EOF
```
Response:
```text
REV: a3f5b7c9d1e2f406 (would be new)
000001:# Plan
000002:    1.1 Parameter and file processing
000003:
000004:## Details
```
For an absolutely empty result, `DRY_ALL` returns:
```text
REV: a3f5b7c9d1e2f406 (would be new)
(Empty file: 0 lines)
```

#### `@APPLY` example
```bash
deck-editor apply file.py - <<'EOF'
@APPLY a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Parameter and file processing
@END
EOF
```
Response:
```text
APPLIED successfully
REV: a3f5b7c9d1e2f406 (new)
Operations applied:
- REPLACE lines 2-2 (1 line replaced with 1 line)
```

### Deck structure
A deck consists of a header, a body, and a terminator.
```text
header      := marker ("DRY" | "DRY_ALL" | "APPLY") <rev>
marker      := "@" | "$"
body        := one or more operations
terminator  := marker "END"
```
Example:
```text
@APPLY a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Parameter and file processing
@END
```

Mandatory rules:
- the header must start with `@DRY`, `@DRY_ALL`, or `@APPLY`;
- `<rev>` is mandatory for an existing file;
- `<rev>` must be a 16-character xxh64 hash;
- the terminator must be the last line of the deck;
- lines after the terminator are forbidden;
- the terminator marker must match the header marker;
- mixing `@` and `$` markers in a single deck is forbidden.

Example with `$` marker:
```text
$APPLY a3f5b7c9d1e2f405
$REPLACE 10
@END
$END
```
Here the payload contains the line `@END`, but it is not a command because the deck marker is `$`.

### Deck operations
| Command | Address | Payload | SKIP | Description |
| --- | --- | --- | --- | --- |
| `@REPLACE <addr>` | `N`, `N-M`, `N-` | yes | allowed | Replace lines |
| `@DELETE <addr>` | `N`, `N-M`, `N-` | no | forbidden | Delete lines |
| `@INSERT <N>` | only `N` | yes | allowed | Insert after line `N` |
| `@INSERT_HEAD` | none | yes | allowed | Insert before line 1 |

Important:
- payload is always passed without line numbers;
- operations in a deck are executed sequentially;
- each subsequent operation works with the result of the previous one;
- line numbers may shift after `REPLACE`, `INSERT`, `INSERT_HEAD`, and `DELETE`;
- `DELETE` strictly has no payload;
- `DELETE` does not support `SKIP`.

Example error:
```text
@APPLY a3f5b7c9d1e2f405
@DELETE 2
extra payload
@END
```
Expected error:
```text
ERROR: unexpected payload after DELETE
```

### Addressing
| Format | Description |
| --- | --- |
| `N` | Single line |
| `N-M` | Lines from `N` to `M` inclusive |
| `N-` | From line `N` to the end of the file |

Restrictions:
- line numbering starts from 1;
- for the range `N-M`, `N ≤ M` must hold;
- `INSERT` accepts only a single address `N`;
- `INSERT_HEAD` does not accept an address.

Example error:
```text
@APPLY a3f5b7c9d1e2f405
@INSERT 2-5
text
@END
```
Expected error:
```text
ERROR: INSERT requires single line address
```

### Markers `@` and `$`
The main marker is `@`.
By default, decks are formed like this:
```text
@APPLY a3f5b7c9d1e2f405
@REPLACE 2
new text
@END
```
The alternative marker is `$`.
It is used if the payload contains valid Deck commands with the `@` marker in the zeroth column, for example:
```text
@END
@REPLACE 1
@INSERT 5
```
In this case, you can use a deck with the `$` marker:
```text
$APPLY a3f5b7c9d1e2f405
$REPLACE 10
@END
@REPLACE 1
$END
```
If the payload contains both `@` and `$` commands in the zeroth column, you should use the main `@` marker and put the conflicting operation at the end of the deck with the `SKIP` modifier.

#### Rule for recognizing a control line
A line is recognized as a Deck command only if the following conditions are met simultaneously:
- the `@` or `$` marker is in the zeroth column;
- a reserved word immediately follows the marker;
- the end of the line or a space immediately follows the word.

Reserved words:
- `DRY`
- `DRY_ALL`
- `APPLY`
- `REPLACE`
- `DELETE`
- `INSERT`
- `INSERT_HEAD`
- `END`

Therefore, regular decorators and annotations are not Deck commands:
```python
@app.route
@property
@staticmethod
@Override
```
Bash variables are also not commands:
```bash
$VAR
$END
```
Indented code physically cannot be confused with a command because the marker is not in the zeroth column.

### `SKIP` modifier
`SKIP` is used only when the payload contains lines that the parser is obliged to recognize as Deck commands.
For example, if you are generating documentation for Deck and the payload contains literal strings:
```text
@END
@REPLACE 1
@INSERT 5
```
Then an operation with `SKIP` is needed.

Rules:
- `SKIP` is a boolean flag;
- `SKIP` takes no arguments;
- the operation with `SKIP` must be the last in the deck;
- any operation after `SKIP` is an error;
- `DELETE` does not support `SKIP`;
- regular decorators, annotations, and variables do not require `SKIP`.

Example error:
```text
@APPLY a3f5b7c9d1e2f405
@REPLACE 1 SKIP 3
text
@END
```
Expected error:
```text
ERROR: SKIP takes no arguments
```

Example error:
```text
@APPLY a3f5b7c9d1e2f405
@INSERT 1 SKIP
text
@INSERT 5
more text
@END
```
Expected error:
```text
ERROR: operation after SKIP
```

### Versions, REV and version conflict
`REV` protects against applying edits to an outdated context.

Typical cycle:
1. read the file via `GET`;
2. get the current `REV`;
3. form a deck with this `REV`;
4. apply the deck via `DRY`, `DRY_ALL`, or `APPLY`.

If the file has changed between reading and applying, Deck will reject the deck:
```text
ERROR: version conflict — file changed
```

After a `version conflict`, it is forbidden to:
- guess new line numbers;
- reapply the old deck;
- rewrite the entire file bypassing `GET`.

You must:
- perform a new `GET`;
- get the current `REV`;
- rebuild the deck.

### Limits
| Limit | Default value | Description |
| --- | --- | --- |
| `MAX_DECK_LINES` | 5000 | total limit of payload lines in a deck |
| `MAX_CREATE_LINES` | 50000 | limit for external `CREATE` |

If the limit is exceeded, the deck or `CREATE` is rejected.

### Security and atomic writing
All file operations are restricted to the workspace root.

Rules:
- for CLI, the workspace root is the current working directory;
- for the MCP server, the workspace is set at startup via `--workspace` or the `WORKSPACE` environment variable;
- if the workspace is not set, the current working directory of the MCP server process is used;
- attempts to go outside the workspace are rejected;
- symbolic links are resolved to the real absolute path;
- a file cannot be modified outside the workspace via a symlink.

Example error:
```text
ERROR: access denied — path outside working directory
```

The result of `APPLY` or `CREATE` is written atomically.
Safe-write is used:
- a temporary file is created in the same directory as the target;
- data is written and flushed via `fsync`;
- the access permissions of the original file are preserved;
- the target file is atomically replaced via `os.replace()`;
- on error, the temporary file is deleted;
- the target file remains untouched.

The file on disk must never end up in a partially written, corrupted, or empty intermediate state.

### MCP server
Deck Editor can work as an MCP server and connect to Qwen Code and other MCP clients.

#### Configuration in Qwen Code
Add to `.qwen/settings.json`:
```json
{
  "mcpServers": {
    "deck-editor": {
      "command": "/path/to/deck/.venv/bin/deck-editor-mcp",
      "args": [
        "--workspace",
        "/path/to/project"
      ]
    }
  }
}
```
Or use a relative path from the project:
```json
{
  "mcpServers": {
    "deck-editor": {
      "command": ".venv/bin/deck-editor-mcp",
      "args": [
        "--workspace",
        "."
      ]
    }
  }
}
```
Alternatively, the workspace can be set via an environment variable:
```json
{
  "mcpServers": {
    "deck-editor": {
      "command": ".venv/bin/deck-editor-mcp",
      "env": {
        "WORKSPACE": "/path/to/project"
      }
    }
  }
}
```

#### Available tools
| Tool | Description |
| --- | --- |
| `get` | Read lines of a file. Returns `REV` and a numbered listing |
| `create` | Create a new file or overwrite an existing one |
| `apply` | Apply a deck to a file. Supports `@DRY`, `@DRY_ALL`, `@APPLY` |

#### `get` call example
Request:
```json
{
  "name": "get",
  "arguments": {
    "file": "src/main.py",
    "addr": "1-50"
  }
}
```
Response:
```text
REV: a3f5b7c9d1e2f405
000001:def main():
000002:    config = load_config()
000003:    result = process(config)
000004:    return result
000005e
000006:def process(config):
...
```

#### Working with files from other projects
According to the specification, the workspace is set at the MCP server startup level, not in the arguments of an individual tool.
For another project, launch a separate MCP server with a different workspace:
```json
{
  "mcpServers": {
    "deck-editor-other-project": {
      "command": ".venv/bin/deck-editor-mcp",
      "args": [
        "--workspace",
        "/home/user/projects/other_project"
      ]
    }
  }
}
```
For CLI, simply run the command from the desired working directory:
```bash
cd /home/user/projects/other_project
deck-editor get src/main.py 1-50
```

### Recommended workflow for LLM agents
Deck is designed with the Unix-way in mind and delegates search to external tools.

Recommended cycle:
1. Text search via `ripgrep`:
   ```bash
   rg -n "calculate_total" src/
   ```
2. Structural search via `ast-grep` if you need to find a function, class, or other syntactic block entirely.
3. Reading context via Deck:
   ```bash
   deck-editor get src/main.py 120-160
   ```
4. Applying the deck:
   ```bash
   deck-editor apply src/main.py - <<'EOF'
   @APPLY a3f5b7c9d1e2f405
   @REPLACE 125-130
   new code
   @END
   EOF
   ```

#### Strict rules for the agent:
- never apply `REPLACE` or `DELETE` to a file that has not been read via `GET` in the current session;
- never omit `REV` in the deck header;
- never guess line numbers;
- on `version conflict`, a new `GET` is mandatory;
- do not use `SKIP` for regular decorators like `@app.route`;
- use `SKIP` only if the payload contains literal Deck commands;
- place the operation with `SKIP` last in the deck;
- always pass the payload without line numbers.

### Errors
On any error, the file on disk is not modified. The deck is rolled back entirely.

Main errors:
| Error | Cause |
| --- | --- |
| `ERROR: deck not terminated by END` | The last line of the deck is not `@END` or `$END` |
| `ERROR: trailing lines after END` | There are lines after the terminator |
| `ERROR: terminator does not match deck marker` | The header uses `@` and the terminator uses `$`, or vice versa |
| `ERROR: deck must start with DRY, DRY_ALL or APPLY` | Invalid deck header |
| `ERROR: <rev> is mandatory for existing files` | `REV` is missing in the deck header |
| `ERROR: unexpected payload after DELETE` | Payload was passed after `DELETE` |
| `ERROR: SKIP takes no arguments` | `SKIP` was specified with arguments |
| `ERROR: operation after SKIP` | There is another operation after the operation with `SKIP` |
| `ERROR: INSERT requires single line address` | `INSERT` was called with a range |
| `ERROR: INSERT_HEAD takes no address` | `INSERT_HEAD` was called with an address |
| `ERROR: version conflict — file changed` | `REV` in the deck does not match the current file hash |
| `ERROR: invalid address range — start > end` | In the address `N-M`, the value `M` is less than `N` |
| `ERROR: address out of file range` | The address is out of the file bounds |
| `ERROR: file does not exist, use CREATE` | `APPLY` was applied to a non-existent file |
| `ERROR: deck size limit exceeded` | `MAX_DECK_LINES` was exceeded |
| `ERROR: access denied — path outside working directory` | The path is outside the workspace |
| `ERROR: file exists, <rev> required to overwrite` | `CREATE` on an existing file without `REV` |
| `ERROR: <rev> must not be specified for new file` | `CREATE` on a non-existent file with `REV` |

The full table of errors and validation stages are described in `spec.md`.

### Quick start
#### For developers (CLI)
```bash
# Install
pip install -e .

# Read file
deck-editor get src/main.py 1-20
```
Example response:
```text
REV: a3f5b7c9d1e2f405
000001:def main():
000002:    config = load_config()
000003:    result = process(config)
000004:    return result
```
Preview changes:
```bash
deck-editor apply src/main.py - <<'EOF'
@DRY a3f5b7c9d1e2f405
@REPLACE 3
    result = process(config, strict=True)
@END
EOF
```
Example response:
```text
REV: a3f5b7c9d1e2f406 (would be new)
Original: a3f5b7c9d1e2f405 → Modified: a3f5b7c9d1e2f406
--- original
+++ modified
@@ -3,1 +3,1 @@
-    result = process(config)
+    result = process(config, strict=True)
Operations applied:
- REPLACE lines 3-3 (1 line replaced with 1 line)
```
Apply changes:
```bash
deck-editor apply src/main.py - <<'EOF'
@APPLY a3f5b7c9d1e2f405
@REPLACE 3
    result = process(config, strict=True)
@END
EOF
```
Example response:
```text
APPLIED successfully
REV: a3f5b7c9d1e2f406 (new)
Operations applied:
- REPLACE lines 3-3 (1 line replaced with 1 line)
```
Check the result:
```bash
deck-editor get src/main.py 1-20
```

#### For LLM agents (MCP)
Configure the MCP server in `.qwen/settings.json`.
Specify the workspace via `--workspace` or `WORKSPACE`.
The LLM agent will get access to the `get`, `create`, and `apply` tools.
The agent reads the file via `get`, records the `REV`, forms a deck, and applies it via `apply`.

Minimal safe scenario:
1. `get` → get `REV` and line numbers
2. `apply @DRY` → check the diff
3. `apply @APPLY` → apply changes
4. `get` → check the result

### Full specification
The full specification of the deck language, architecture, and implementation details are in `[spec.md](spec.md)`.
Additional documentation for LLM agents is in `[agents.md](agents.md)`.

### Project structure
```text
deck/
  ├── deck_editor/
  │   ├── __init__.py          — package version
  │   ├── __main__.py          — CLI (get, create, apply)
  │   ├── mcp_server.py        — MCP server
  │   ├── parser.py            — deck parser
  │   ├── cmd_get.py           — GET command
  │   ├── cmd_create.py        — CREATE command
  │   ├── operations.py        — REPLACE, DELETE, INSERT
  │   ├── apply.py             — DRY, DRY_ALL, APPLY
  │   └── utils.py             — xxhash, atomic_write, errors
  ├── tests/                   — tests
  ├── doc/                     — additional documentation
  ├── spec.md                  — full specification
  ├── agents.md                — rules for LLM agents
  ├── pyproject.toml           — package configuration
  └── README.md                — this file
```
