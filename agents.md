# AGENTS.md: Rules for the AI Agent in the Deck Project

## 1. Role and Philosophy
You are a highly skilled AI agent working with a codebase. You do not edit files directly. You use the transactional editor **Deck**, which operates on the principle of batch processing (punch cards).
Your task is to formulate atomic "decks" of commands that are applied to files entirely or not applied at all.

## 2. Hard Rules (Thou Shalt Nots)
1. **NEVER guess line numbers.** If you haven't read the file via `deck_get` in the current session, you are not allowed to generate a deck for it.
2. **NEVER rewrite entire files (Rewrite Anti-Pattern).** You are forbidden from using `deck_create` to overwrite an existing file if you can make precise edits via a deck (`deck_apply`). A full rewrite is only permissible when creating a brand new file.
3. **NEVER ignore `version conflict`.** If the editor returns `ERROR: version conflict — file changed`, your context is stale. Stop, execute `deck_get` again, obtain the actual `<rev>`, and rebuild the deck.
4. **NEVER pass line numbers in the payload.** Line numbers (e.g., `000001:`) are returned by the editor. In `REPLACE`, `INSERT` commands, and the `CREATE` stream, you must pass **only clean text**.
5. **NEVER use `sed`, `awk`, `patch`, or `perl -pi`.** These tools do not exist in this environment. The **only** editing tool is Deck. There is no "simple case" for sed — every file modification is a deck.

## 3. Prohibition on "Simplification"
A 4-line deck is **not** overkill for a single-line change. It is the minimum and **only** form of editing.

- Do NOT attempt to "simplify" a deck by omitting the header or terminator.
- Do NOT generate an entire file instead of a 4-line deck.
- Do NOT look for alternative editing tools. They do not exist.

A 4-line deck is always cheaper than one `sed` command followed by three retries and a final full-file rewrite.

## 4. Standard Workflow
For any code modification task, strictly adhere to this cycle:

1. **Reconnaissance (Search):** Use external tools (`ripgrep` for text, `ast-grep` for structural blocks) to find the exact line numbers of your target.
2. **Reading (Read):** Call `deck_get <file> <addr>` to fetch the context and lock in the `<rev>`.
3. **Planning (Plan):** Formulate the deck mentally. Check if there are any `@` or `$` characters in the payload at column zero.
4. **Application (Apply):** Choose the application mode:

   | Condition | Action |
   |-----------|--------|
   | Edit ≤ 20 lines, addressing is obvious, file is not critical | `@APPLY <rev>` directly |
   | Edit > 20 lines, OR addressing is uncertain, OR file is critical | `@DRY <rev>` first → verify diff → then `@APPLY <rev>` |

   **Default is `@APPLY`.** Use `@DRY` only when you have a concrete reason to doubt the result.

   **The error-free path is: `get` → `@DRY` → `@APPLY` → verification (see below).** Every step you skip removes one checkpoint where a mistake would otherwise be caught before it reaches disk or before it goes unnoticed. Skipping `@DRY` is a token/latency trade-off, not a correctness improvement — make it deliberately, not by default.

   **Verification (recommended):** Deck guarantees the write was atomic and applied at the addresses you specified — it does not know or check whether the resulting content is valid for the file's language. After a non-trivial `@APPLY`, verify the result yourself with whatever tool fits the language (e.g. `python -m py_compile`, `node --check`, `go build`, a linter, the project's test suite). This is a separate step performed with your existing tools, not a mode of Deck.

## 5. Error Handling
When you receive an error from Deck, the file on disk remains unchanged. Analyze the error:
- `ERROR: version conflict` → Context is stale. Perform a new `deck_get`.
- `ERROR: address out of file range` → You exceeded the file boundaries. Check `deck_get`.
- `ERROR: deck not terminated by END` → You forgot the terminator `@END` or `$END`.
- `ERROR: terminator does not match deck marker` → You started the deck with `@` but ended it with `$END` (or vice versa).
- `ERROR: operation after SKIP` → You placed an operation after a `SKIP` operation. `SKIP` must be the last operation before `@END`.

## 6. Token Economy
- Do not read the entire file (`deck_get file 1-`) if the file is large. Read only the necessary range around the target.
- Use `@DRY` instead of `@APPLY` **only** for large or uncertain edits (see Section 4). For routine edits, `@APPLY` directly is more token-efficient.

## 7. Unicode and Emoji
- `REPLACE_REGEX` works with full Unicode: emoji, CJK characters, accented Latin, ZWNJ-joined grapheme clusters.
- You can replace specific emoji in a string with multiple emoji: `s/🎉/party/g` replaces only the party emoji, leaving others untouched.
- Complex emoji (e.g. `👨‍👩‍👧‍👦`) are single grapheme clusters — match them literally in the pattern.
- Use different delimiters (`|`, `#`, `~`) if the pattern contains `/`.
- Example: `s/🔥/fire/g`, `s/测试/test/g`, `s/👨‍👩‍👧‍👦/family/g`.
