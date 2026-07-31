Here is the English translation:

Punch Cards for LLMs: an editor that lets a neural network edit code like in the 1960s

Prologue: how it was, and why “punch cards”

Imagine the 1960s. A programmer is sitting not at a terminal, but at a keypunch — a device resembling a huge typewriter. Very often it is not even the programmer themselves, but a specially trained operator: a woman from the keypunch room, who transfers handwritten code onto cards. She types the lines, and the machine punches rows of rectangular holes in a stiff cardboard card. Above the punching, the text itself is printed so that a person can read it visually.

Each card is one line — one instruction or one statement. A finished program is not a file on disk, but a deck of such cards, bound with a rubber band. And here is what matters: each card carried a line number in its last columns. This was not merely decoration, but a mandatory element. Dropping the deck and mixing it up was unpleasant, but not catastrophic. All the work of restoring order — sorting, checking whether all cards were in place — was performed by the operating system right inside the computer.

Today’s LLMs are in the same position as a programmer in the 1960s. They have no monitor to see a file and immediately make a change. To understand what to edit, the model must first “print out” the whole file or a piece of it — request it through a separate command. And to change it — apply an editor that must be told exactly what to replace with what. Humans have long looked at monitors and edited text directly; tools for blind editing died with punch cards. But LLMs were left without them.

We recreated these tools: packaged them as an MCP server (Model Context Protocol), give the model a “deck” of control commands with line numbers, and the editor applies them to the original file snapshot atomically — all or nothing.

Why models give up and suggest rewriting the whole file

If you have worked with local LLMs for code editing, you have surely seen this scene: the model tries to make several edits, suffers 2–3 failures, and then writes: “I think I got confused. Let me rewrite the entire file.”

This is not a bug of a particular model — it is a systemic problem with two different failure mechanics depending on the tool.

`str_replace` fails because of textual mismatch. The model looks for a unique piece of text in the file to replace it — and if it is not unique (a repeating code block), or if the model hallucinates an extra space/indent, the replacement is rejected entirely. In the issue tracker of the popular agentic editor Cline, there is a separate mega-issue devoted to this — `replace_in_file` failures with fallback to a full file rewrite, plus two dozen related issues about the same failure pattern.

Diffs (unified diff, udiff, `git apply`) fail because of line-number shifts. Change line 10 — and the header `@@ -20,5 +20,5 @@`, honestly calculated by the model before that edit, no longer matches the actual file. Generating a valid diff requires exact recalculation of offsets after every previous edit in the same patch, and that is exactly the type of sequential computation where weak models make mistakes. Aider’s official documentation openly admits: most local models are “barely capable” of working with its edit format, and recommends the `--edit-format whole` flag for them — that is, switching the model to full file rewriting as the main working mode.

In both cases, the outcome is the same: after several failed attempts, the model loses confidence in its “mental image” of the file and proposes a radical solution — rewrite everything. This is expensive (thousands of tokens), risky (the model may forget code that should not be touched), and turns a readable diff into mush.

Deck solves both problems, but not by eliminating recalculation — by making it trivial. Addressing by line numbers removes the need for exact text matching (unlike `str_replace`). Operations inside one deck still execute sequentially, each against the result of the previous one, so addresses can shift within a multi-operation deck exactly as they would with manual sequential edits — but the model only ever tracks a single integer, not a two-sided diff hunk header. A model unsure of the exact shift can even sidestep the arithmetic entirely: instead of computing `DELETE 8-10`, it can emit `DELETE 8` three times in a row, since each deletion shifts the next line into position 8. The model copies the numbers it sees in the `GET` output and, where an edit changes the line count, follows the shift one step at a time — not the multi-hunk bookkeeping that unified diff demands.

How the editor works

Reading: `GET`

The model reads the file not as a whole, but in parts via the `GET` command, receiving a numbered listing:

```text
REV: a3f5b7c9d1e2f406
000001:import sys
000002:import os
000003e
000004:def main():
000005:    print("Hello")
```

The numbers are not part of the file; they are added by the editor only for reading. Six digits, with an `e` suffix for empty lines. Along with the listing, the model receives the current file-state hash (`REV`) — an xxh64 hash. This hash is the key to protecting against version races. The model remembers it during reading and includes it in the deck header. If the file changes while the model is thinking (a linter, IDE, or parallel process), the editor will reject the entire deck and say: `version conflict`. The model will not trample someone else’s changes; instead, it will get a chance to reread the file.

Deck: structure

A deck is a packet of commands applied to a file atomically. The structure is strictly fixed:

```text
@APPLY a3f5b7c9d1e2f406
@REPLACE 42
    new line text
@END
```

Three mandatory parts:

- Header — the marker, command, and hash: `@APPLY <rev>`, `@DRY <rev>`, or `@DRY_ALL <rev>`.
- Body — one or more operations.
- Terminator — `@END`. Always the last line. Without it, the deck is rejected in full.

The terminator is not a formality. It is a guard clause against generation cutoff. If the model has exhausted its token limit and cut off the response in the middle of the payload, the parser sees the absence of `@END` and immediately rejects the deck. The file on disk is not touched. No partial application.

Operations

The commands are as simple as possible:

- `@REPLACE <addr>` — replace lines. Address: `N`, `N-M`, `N-`.
- `@DELETE <addr>` — delete lines. No payload.
- `@INSERT <N>` — insert text after line `N`.
- `@INSERT_HEAD` — insert text at the very beginning of the file.

Multiple operations in a deck are executed sequentially: each one operates on the result of the previous one, exactly as if applied one at a time. This means addresses inside a multi-operation deck are relative to the file **as it stands after the preceding operations in the same deck**, not to the original `GET` snapshot — if an earlier operation adds or removes lines, every following address must account for that shift. It is deliberately simple arithmetic (one line number to track, not a two-sided diff header to keep in sync), and it can be sidestepped further: a model unsure of an exact shift can repeat a single-line operation instead of computing a range.

Marker and SKIP

The main marker is `@`. The alternative is `$`. The marker is chosen in the header and applies to the entire deck; mixing is not allowed.

A line is recognized as a command only when the following conditions are met simultaneously: a marker in column zero, followed by a reserved keyword (`REPLACE`, `DELETE`, `INSERT`, `INSERT_HEAD`, `END`, `APPLY`, `DRY`, `DRY_ALL`), followed by the end of the line or a space. A Python decorator `@app.route` or a bash variable `$VAR` is not a command — the words `app.route` and `VAR` are not reserved.

A conflict occurs only if the payload literally contains `@END` or `@REPLACE` in column zero (for example, if you are generating documentation for Deck itself). For this, there is the `SKIP` modifier: an operation with `SKIP` is placed at the end of the deck, and all text up to `@END` is treated as payload without scanning for commands. `SKIP` is a boolean flag, with no arguments.

DRY: preview

For large (more than 20 lines) or uncertain edits, there is `@DRY <rev>` — it returns a unified diff without touching the file. The model checks it, then generates the same deck with `@APPLY`. For routine edits, `@DRY` is not needed — it is an extra step.

CREATE: new file

`CREATE` is an external command, not part of a deck. It reads content from stdin until EOF. The payload is not scanned for control words, so markers and terminators are not required. You can safely create bash scripts with `$VAR` and `$END` in column zero.

When overwriting an existing file, `<rev>` is mandatory. For a new file, `<rev>` must not be specified. In response, the editor returns a full numbered listing of the result — the model learns the line numbers without an additional `GET`.

Navigating 50,000-line monoliths

The model is not required to read the whole file. It uses classic search (for example, `ripgrep`) integrated into its environment. The command `rg -n -C 3 "def process_data" main.py` gives the model a numbered “printout”:

```text
39-
40-    # Raw data processing
41-    @retry(max_attempts=3)
42:    def process_data(self, data):
43-        """Main pipeline method"""
44-        if not data:
45-            raise ValueError("Data is empty")
```

After receiving such a response, the model orients itself within the file’s space. It does not need to load the whole monolith into context — it sees the exact coordinates and surrounding lines. Then it requests a narrow range via `GET`, records `REV`, and forms a deck: `@REPLACE 42-45` or `@INSERT 45`.

For structural search (finding an entire function, including its body), `ast-grep` is used. It understands the language syntax and returns exact boundary lines, which map directly to `REPLACE N-M`.

Why only lines and no characters

A punch card is always an entire line. You could not replace a hole in the middle of a card — you replaced the whole card (although there were eccentrics who patched the holes with pieces of cardboard — “confetti” left over from punching cards — and were proud of it). We adopted this principle: the editor has no operations on individual characters or columns. Only line-based commands.

This decision did not come immediately. Initially, there was support for character addressing like `@REPLACE 10:5-12`. But it quickly became clear that Unicode turns character counting into a minefield. The model sees the emoji “👨‍👩‍👧‍👦” as one grapheme, while Python sees it as seven code points. The model cannot predict what position a letter will occupy after such a character. Character addressing was removed completely — and the positioning problems disappeared.

Why not str_replace_editor and not Aider?

`str_replace_editor` (popularized by Anthropic and SWE-bench). The model searches for a unique piece of text and replaces it. It breaks if the text is not unique, if the model hallucinates extra spaces, or if the code contains indistinguishable duplicate blocks.

Diffs (as in Aider). The model generates a standard `git diff` or unidiff. Generating a valid diff with correct `+`, `-`, and `@@` requires a high degree of logical discipline from the model. Weak and local models regularly confuse characters, mess up headers, and break the patch.

Deck solves both problems. Line numbers are hard coordinates; they cannot be “hallucinated” (the model copies them from `GET` or `ripgrep` output). An atomic deck eliminates diff syntax errors. `version conflict` guarantees that edits are applied to the file the model read, not to a phantom from its memory.

Try it

Deck is written in Python and runs as a standard MCP server.

Three tools the model receives via MCP:

- `deck_get(file, addr)` — read a numbered line range and get `REV`.
- `deck_create(file, content, rev)` — create a new file or completely overwrite an existing one.
- `deck_apply(file, deck)` — apply a deck of edits.

CLI for working from the shell:

```bash
deck-editor get main.py 40-50
deck-editor create new_file.py < content.txt
deck-editor apply main.py < deck.txt
```

You may find it useful.

Instead of a conclusion

We did not invent anything fundamentally new. We remembered how programmers worked with code more than half a century ago and applied the same principles to LLMs. It turned out that punch cards — with their decks, explicit numbers, and atomic application — fit the needs of language models. Once, a machine sorted cards to help a human. Now it applies decks to help artificial intelligence. Perhaps this is the best compliment to the engineers of the past, who built systems understandable without words.
