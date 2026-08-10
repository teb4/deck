---
name: deck-editor
description: Transactional editing skill using Deck MCP server for precise file modifications with atomic apply and dry-run preview.
---

# SKILL.md: Transactional Editing Skill (Deck MCP)

## Tool Description
Deck is a transactional editing language. You interact with it via an MCP server.

## MCP Server Usage

You interact with Deck through **three MCP tools**. Each tool is called as a separate MCP request.

### Calling MCP Tools

```json
// Example: calling deck_get
{
  "name": "deck_get",
  "arguments": {
    "file": "src/main.py",
    "addr": "10-20"
  }
}
```

```json
// Example: calling deck_apply
{
  "name": "deck_apply",
  "arguments": {
    "file": "src/main.py",
    "deck": "@APPLY a1b2c3d4e5f6\n@REPLACE 15\ndef new_func():\n    pass\n@END"
  }
}
```

```json
// Example: calling deck_create (new file)
{
  "name": "deck_create",
  "arguments": {
    "file": "src/new_module.py",
    "content": "def hello():\n    return 'world'\n"
  }
}
```

### Response Format

**`deck_get` response:**
```
REV: a1b2c3d4e5f6
000001:def foo():
000002:    pass
000003e
000004:def bar():
```

**`deck_apply` response (success):**
```
APPLIED successfully
REV: b2c3d4e5f6a1b2c3 (new)
Operations applied:
- REPLACE lines 15-15 (1 line replaced with 2 lines)
```

**`deck_apply` response (error):**
```
ERROR: version conflict — file changed
```

**`deck_create` response:**
```
REV: c3d4e5f6a1b2c3d4
000001:def hello():
000002:    return 'world'
```

## Complete Workflow

### Standard Edit Cycle
1. **Search** — find the target using `ripgrep` (`rg -n "pattern" file.py`) or `ast-grep`.
2. **Read** — call `deck_get(file, "N-M")` to read the context. **Save the `<rev>` from the response.**
3. **Plan** — decide which operation(s) you need. Check if payload contains `@` or `$` at column zero.
4. **Apply** — call `deck_apply(file, deck_text)`.
5. **Verify** — call `deck_get(file, "N-M")` again to confirm the changes.

### Safe Edit Cycle (recommended for non-trivial edits)
1. `deck_get` → save `<rev>`
2. `deck_apply` with `@DRY <rev>` → check the diff
3. `deck_apply` with `@APPLY <rev>` → apply changes
4. `deck_get` → verify the result

### Creating a New File
1. Call `deck_create(file, content)` — **do NOT pass `<rev>`**.
2. The response contains the new `<rev>` and the full numbered listing.

### Overwriting an Existing File
1. Call `deck_get(file, "1-")` → get the current `<rev>`.
2. Call `deck_create(file, content, rev="<rev>")` — **pass the `<rev>`**.

## Error Handling

| Error | What to do |
|-------|------------|
| `ERROR: version conflict — file changed` | Context is stale. Call `deck_get` again, get new `<rev>`, rebuild the deck. |
| `ERROR: address out of file range` | You exceeded file boundaries. Call `deck_get` to see actual line count. |
| `ERROR: deck not terminated by END` | You forgot `@END` or `$END`. Always include it. |
| `ERROR: terminator does not match deck marker` | Header uses `@`, terminator uses `$END` (or vice versa). Match them. |
| `ERROR: file exists, <rev> required to overwrite` | `deck_create` on existing file without `<rev>`. Call `deck_get` first. |
| `ERROR: <rev> must not be specified for new file` | `deck_create` on non-existent file with `<rev>`. Remove `<rev>`. |
| `ERROR: unexpected payload after DELETE` | `DELETE` has no payload. Remove any text between `@DELETE N` and `@END`. |
| `ERROR: operation after SKIP` | `SKIP` must be the last operation. Move other operations before it. |
| `ERROR: INSERT requires single line address` | `INSERT` accepts only `N`, not `N-M`. |
| `ERROR: invalid sed expression` | `REPLACE_REGEX` payload must be `s/pattern/replacement/flags`. |

## Available MCP Tools

### 1. `deck_get(file: str, addr: str)`
Reads a range of lines. Returns numbered text and the `<rev>` hash.
- `file`: path to the file (relative to workspace root).
- `addr`: `N` (single line), `N-M` (range), `N-` (to the end of the file).
- **Response includes `REV` — save it for the next `deck_apply` or `deck_create`.**

### 2. `deck_create(file: str, content: str, rev: str | None)`
Creates a new file or completely overwrites an existing one.
- `file`: path to the file (relative to workspace root).
- `content`: the full file content as a string.
- `rev`: required for overwriting existing files, forbidden for new files.
- **Use only for new files or when >50% of lines change. For targeted edits, use `deck_apply`.**

### 3. `deck_apply(file: str, deck: str)`
Applies a deck of commands to an existing file.
- `file`: path to the file (relative to workspace root).
- `deck`: a string containing the full deck text (header, operations, terminator).
- **The file must exist — use `deck_create` for new files.**
- **Deck is applied atomically — all or nothing.**

---

## Deck Syntax (Grammar)

A deck consists of three parts: **Header**, **Body**, **Terminator**.

```text
<marker><COMMAND> [<rev>]       <-- Header (choose @ or $)
<marker><OPERATION> [addr] [SKIP]  <-- Body (one or more)
<payload text without line numbers>
...
<marker>END                     <-- Terminator (mandatory at the end!)
```

### Header Commands
| Command | Effect |
|---------|--------|
| `@APPLY <rev>` | Apply and write to disk. **Default choice.** |
| `@DRY <rev>` | Preview: returns a diff. Does NOT modify the file. Use for large (>20 lines) or uncertain edits. |
| `@DRY_ALL <rev>` | Preview: returns a full numbered listing. Does NOT modify the file. Rarely needed. |

**Rule:** After a successful `@DRY`, you must generate the **same deck** with `@APPLY` to actually write. `@DRY` does not modify the file.

### Markers
- `@` (Default). Use it always, except when the payload contains many `@` at column zero.
- `$` (Alternative). Use it if the payload contains `@` at column zero.

*Rule:* The header and terminator markers must match. Mixing `@` and `$` within a single deck is not allowed.

### Operations
- `REPLACE <addr>`: Replaces lines. Address: `N`, `N-M`, `N-`.
- `DELETE <addr>`: Deletes lines. **Has NO payload!**
- `INSERT <N>`: Inserts text **AFTER** line N. Address is only a single `N`.
- `INSERT_HEAD`: Inserts text at the very beginning of the file. No address is specified.
- `REPLACE_REGEX <addr>`: Applies a sed-style regex substitution to lines in range. Address: `N`, `N-M`, `N-`. Payload is a single sed expression: `s/pattern/replacement/flags`. Supports `SKIP` (rarely needed — regex payload is a single line).
- `APPEND`: Appends text to the end of the file. **No address. No `SKIP`.** Payload is one or more lines to append.

### SKIP Modifier ("Dirty Payload Last" Strategy)
If your payload contains the marker character (`@` or `$`) at column zero (e.g., a Python decorator `@app.route` or a Bash variable `$VAR`), the parser might break.

**Solution:**
1. Put this operation at the **very end** of the deck.
2. Add the `SKIP` flag after the address.
3. All text up to the `<marker>END` will be considered the payload for this operation. The parser will stop looking for commands.

`SKIP` is a **boolean flag with no parameters**. Do NOT write `SKIP 5` or `SKIP N`.

---

## When to Use DRY vs APPLY

| Situation | Header |
|-----------|--------|
| Routine edit, ≤ 20 lines, obvious addressing | `@APPLY <rev>` |
| Large edit, > 20 lines | `@DRY <rev>` → verify → `@APPLY <rev>` |
| Uncertain addressing | `@DRY <rev>` → verify → `@APPLY <rev>` |
| Creating a new file | `deck_create` (no deck needed) |

**When in doubt, use `@DRY`.** A wrong `@APPLY` can corrupt the file. A wrong `@DRY` just wastes one extra call.

Deck only guarantees atomic writes at the addresses you specified — it does not validate language syntax. After a non-trivial `@APPLY`, verify with your language tools (`python -m py_compile`, `go build`, tests, etc.).

---

## Examples (Few-Shot)

### Example 1: Simple Replacement (APPLY — default)
*Task: Replace a function on lines 10-12. Edit is small and obvious.*
```text
@APPLY a1b2c3d4e5f6
@REPLACE 10-12
def new_calculate():
    return 42
@END
```

### Example 2: Insertion and Deletion (APPLY — default)
*Task: Delete original line 5 and insert a new import after line 2. Routine edit.*
```text
@APPLY a1b2c3d4e5f6
@INSERT 2
import sys
@DELETE 6
@END
```
*(Note: Operations execute sequentially, and each one works on the result of the previous one. `@INSERT 2` shifts every line after it down by one, so the original line 5 is now line 6 — that's why `@DELETE` addresses `6`, not `5`. Always recompute addresses for every operation after the first one in a multi-operation deck; never reuse the numbers from your original `GET`.)*

### Example 3: Large Edit with DRY Preview
*Task: Replace a 40-line function. Edit is large — preview first.*

**Step 1: Preview**
```text
@DRY a1b2c3d4e5f6
@REPLACE 100-140
def new_large_function():
    # ... 38 lines of new code ...
    return result
@END
```
*Server returns a diff. You verify it looks correct.*

**Step 2: Apply (same deck, header changed)**
```text
@APPLY a1b2c3d4e5f6
@REPLACE 100-140
def new_large_function():
    # ... 38 lines of new code ...
    return result
@END
```

### Example 4: Using SKIP for a Bash Script
*Task: Replace lines 20-22 with a bash script that has `$` at column zero.*
```text
@APPLY a1b2c3d4e5f6
@REPLACE 20-22 SKIP
#!/bin/bash
echo "Starting..."
$VAR="test"
if [ -f "$FILE" ]; then
    echo "Found"
fi
@END
```
*(Since SKIP is used, the parser ignores `$VAR` and `$FILE` at column zero. This operation must be the last one before `@END`.)*

### Example 5: Errors (How NOT to do it)
```text
# ERROR: No terminator
@APPLY a1b2c3d4e5f6
@REPLACE 1
new text

# ERROR: Passing line numbers in the payload
@APPLY a1b2c3d4e5f6
@REPLACE 1
00001:new text
@END

# ERROR: SKIP with a parameter (SKIP is boolean, no arguments)
@APPLY a1b2c3d4e5f6
@REPLACE 1 SKIP 3
text
@END

# ERROR: Operation after SKIP
@APPLY a1b2c3d4e5f6
@REPLACE 1 SKIP
text with @decorator
@INSERT 5
more text
@END
```

### Example 6: REPLACE_REGEX — Regex Substitution
*Task: Replace all occurrences of "foo" with "bar" in lines 4–50.*
```text
@APPLY a1b2c3d4e5f6
@REPLACE_REGEX 4-50
s/foo/bar/g
@END
```

### Example 7: REPLACE_REGEX — Capture Groups
*Task: Replace "temp" with "temp_celsius" using capture groups.*
```text
@APPLY a1b2c3d4e5f6
@REPLACE_REGEX 10-20
s/(temp)/\1_celsius/g
@END
```

### Example 8: APPEND — Add Lines to End of File
*Task: Append a JSON log entry to the end of a file.*
```text
@APPLY a1b2c3d4e5f6
@APPEND
{"sensor": "temp", "value": 30.0, "unit": "C"}
@END
```

### Example 9: APPEND — Multiple Lines
*Task: Append multiple JSON objects.*
```text
@APPLY a1b2c3d4e5f6
@APPEND
{"sensor": "humidity", "value": 65.0, "unit": "%"}
{"sensor": "pressure", "value": 1013.0, "unit": "hPa"}
@END
```

### Example 10: REPLACE_REGEX — Different Delimiters
*Task: Replace paths using `#` as delimiter (avoids escaping slashes).*
```text
@APPLY a1b2c3d4e5f6
@REPLACE_REGEX 1-100
s#/usr/local/bin#/opt/bin#g
@END
```

### Example 11: REPLACE_REGEX — Unicode Emoji
*Task: Replace a specific emoji in a string with multiple emoji.*
```text
# Input: 🔥🎉✨🚀💥
@APPLY a1b2c3d4e5f6
@REPLACE_REGEX 1
s/🎉/party/g
@END
# Result: 🔥party✨🚀💥
```

### Example 12: REPLACE_REGEX — CJK Characters
*Task: Replace Chinese characters.*
```text
# Input: 测试测试测试
@APPLY a1b2c3d4e5f6
@REPLACE_REGEX 1
s/测试/test/g
@END
# Result: testtesttest
```

### Example 13: REPLACE_REGEX — Complex Emoji (ZWNJ Grapheme Cluster)
*Task: Replace a family emoji (👨‍👩‍👧‍👦) — a single grapheme made of multiple code points.*
```text
# Input: Hello 👨‍👩‍👧‍👦 world
@APPLY a1b2c3d4e5f6
@REPLACE_REGEX 1
s/👨‍👩‍👧‍👦/family/g
@END
# Result: Hello family world
```

### Example 14: REPLACE_REGEX — Accented Characters
*Task: Replace accented characters across multiple lines.*
```text
# café → cafe, résumé → resume (all occurrences in lines 1–10)
@APPLY a1b2c3d4e5f6
@REPLACE_REGEX 1-10
s/é/e/g
@END
```

### Example 15: APPEND — No Address, No SKIP
*Task: Append a line. Note: `APPEND` takes no address and does not support `SKIP`.*
```text
@APPLY a1b2c3d4e5f6
@APPEND
new line at end
@END
```

### Example 16: Errors — APPEND
```text
# ERROR: SKIP is not supported for APPEND
@APPLY a1b2c3d4e5f6
@APPEND SKIP
some text
@END

# ERROR: APPEND with address
@APPLY a1b2c3d4e5f6
@APPEND 5
text
@END
```
