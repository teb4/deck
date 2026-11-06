"""Основная логика CLI Deck Editor."""

import argparse
import sys

from deck_editor.apply import apply as apply_impl
from deck_editor.cmd_create import cmd_create
from deck_editor.cmd_get import cmd_get, get_rev_and_count
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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deck-editor",
        description="Deck Editor — transactional text editor for LLM agents",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # GET
    get_parser = subparsers.add_parser("get", help="Read file lines")
    get_parser.add_argument("file", help="Path to file")
    get_parser.add_argument("addr", help="Address range (e.g. 1-50)")

    # REV
    rev_parser = subparsers.add_parser("rev", help="Return only REV hash and line count")
    rev_parser.add_argument("file", help="Path to file")

    # CREATE
    create_parser = subparsers.add_parser("create", help="Create or overwrite file from stdin")
    create_parser.add_argument("file", help="Path to file")
    create_parser.add_argument("rev", nargs="?", default=None, help="Current rev (required for overwrite)")

    # APPLY
    apply_parser = subparsers.add_parser("apply", help="Apply a deck to a file")
    apply_parser.add_argument("file", help="Path to file")
    apply_parser.add_argument("deck", nargs="?", default=None, help="Deck file (use - for stdin)")

    args = parser.parse_args()

    # Определяем workspace root (текущая директория)
    workspace_root = "."

    if args.command == "get":
        file_path = validate_path(args.file, workspace_root)
        cmd_get(file_path, args.addr)

    elif args.command == "rev":
        file_path = validate_path(args.file, workspace_root)
        try:
            file_rev, total_lines = get_rev_and_count(file_path)
        except FileNotFoundError:
            print(format_error(
                FileNotFoundError(f"file not found — {args.file}"),
                hint="check that the path is correct and the file exists in the workspace."),
                file=sys.stderr)
            sys.exit(1)
        except AccessDeniedError as exc:
            print(format_error(exc, hint="the path is outside the working directory."),
                  file=sys.stderr)
            sys.exit(1)
        print(f"REV: {file_rev}")
        print(f"LINES: {total_lines}")

    elif args.command == "create":
        file_path = validate_path(args.file, workspace_root)
        try:
            cmd_create(file_path, args.rev)
        except (VersionConflictError, ValueError) as exc:
            print(format_error(exc), file=sys.stderr)
            sys.exit(1)

    elif args.command == "apply":
        file_path = validate_path(args.file, workspace_root)
        deck_text = read_deck_input(args.deck)
        try:
            deck = parse_deck(deck_text)
        except DeckSyntaxError as exc:
            print(format_error(exc), file=sys.stderr)
            sys.exit(1)
        apply_deck(file_path, deck, workspace_root)


def read_deck_input(deck_path: str) -> str:
    """Читает колоду из файла или stdin."""
    if deck_path == "-":
        return sys.stdin.read()
    if deck_path is not None:
        with open(deck_path, "r", encoding="utf-8") as fh:
            return fh.read()
    # По умолчанию читаем из stdin
    return sys.stdin.read()


def apply_deck(file_path: str, deck, workspace_root: str) -> None:
    """Применяет колоду к файлу."""
    try:
        result = apply_impl(file_path, deck, workspace_root)
    except VersionConflictError as exc:
        print(format_error(exc), file=sys.stderr)
        sys.exit(1)
    except AddressError as exc:
        print(format_error(exc), file=sys.stderr)
        sys.exit(1)
    except DeckSyntaxError as exc:
        print(format_error(exc), file=sys.stderr)
        sys.exit(1)
    except DeckLimitError as exc:
        print(format_error(exc), file=sys.stderr)
        sys.exit(1)
    except AccessDeniedError as exc:
        print(format_error(exc), file=sys.stderr)
        sys.exit(1)

    print(result)
