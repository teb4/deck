# SKILL.md: Transactional Editing Skill (Deck MCP)

## Tool Description
Deck is a transactional editing language. You interact with it via an MCP server.

## Available MCP Tools

### 1. `deck_get(file: str, addr: str)`
Reads a range of lines. Returns numbered text and the `<rev>` hash.
- `addr`: `N` (single line), `N-M` (range), `N-` (to the end of the file).

### 2. `deck_create(file: str, rev: str | None)`
Creates a new file or completely overwrites an existing one.
- Reads text from `stdin` (in MCP, this is the `content` argument).
- If the file exists, you **MUST** pass the current `<rev>`. If the file does not exist, do not pass `<rev>`.

### 3. `deck_apply(file: str, deck: str)`
Applies a deck of commands to an existing file.
- `deck`: a string containing the full deck text (header, operations, terminator).

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
| Uncertain addressing (you're not 100% sure about line numbers) | `@DRY <rev>` → verify → `@APPLY <rev>` |
| Critical file (production config, migration, etc.) | `@DRY <rev>` → verify → `@APPLY <rev>` |
| Creating a new file | `deck_create` (no deck needed) |

**Default is `@APPLY`.** Do not use `@DRY` "just in case" for every edit — it doubles the number of decks you generate and wastes tokens.

**The error-free path is `get` → `@DRY` → `@APPLY` → verification.** Deck itself only guarantees that the write is atomic and lands at the exact addresses you specified — it does not know or check whether the resulting content is valid for the file's language (e.g. it will happily write a Python file with broken indentation if that's what the payload contained). After a non-trivial `@APPLY`, verify the result with whatever tool fits the language (`python -m py_compile`, a linter, `go build`, the test suite, etc.) — that verification is your job with your existing tools, not something Deck does for you.

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
