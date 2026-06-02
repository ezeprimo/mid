"""CLI entry point — argument parsing, handler dispatch, exit codes.

Exit codes
----------
* 0 – success
* 1 – conversion error (MarkItDown / converter failure)
* 2 – argument error (missing file, invalid flag, etc.)
* 3 – unsupported format (including legacy .doc / .xls / .ppt)
"""

import argparse
import json
import sys
from pathlib import Path

from mid import __version__
from mid.engine import REGISTRY, convert_file, resolve_converter

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def setup_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="mid",
        description="Convert documents to Markdown using Microsoft MarkItDown",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"mid {__version__}",
        help="show version and exit",
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="list supported file formats and exit",
    )

    sub = parser.add_subparsers(dest="command", help="available commands")

    # -- convert -----------------------------------------------------------
    conv = sub.add_parser("convert", help="convert a single file to Markdown")
    conv.add_argument("file", nargs="?", help="path to the input file")
    conv.add_argument("-o", "--output", help="write output to FILE instead of stdout")
    conv.add_argument("--json", action="store_true", help="emit JSON with metadata")

    # -- batch -------------------------------------------------------------
    bat = sub.add_parser("batch", help="convert all supported files in a directory")
    bat.add_argument("input", nargs="?", help="input directory")
    bat.add_argument("-o", "--output", help="output directory")
    bat.add_argument("--recursive", action="store_true", help="process subdirectories")
    bat.add_argument("--flatten", action="store_true", help="flatten output structure (requires --recursive)")
    bat.add_argument("--preserve", action="store_true", help="preserve directory structure in output")

    # -- help subcommand ---------------------------------------------------
    hp = sub.add_parser("help", help="show help for a command")
    hp.add_argument("topic", nargs="?", help="command to show help for")

    return parser


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _exit_arg(msg: str) -> None:
    """Print an argument error to stderr and exit with code 2."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def _exit_fmt(msg: str) -> None:
    """Print an unsupported-format error to stderr and exit with code 3."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(3)


def _exit_conv(msg: str) -> None:
    """Print a conversion error to stderr and exit with code 1."""
    print(f"error: conversion failed: {msg}", file=sys.stderr)
    sys.exit(1)


# -- convert handler -------------------------------------------------------


def handler_convert(args: argparse.Namespace) -> None:
    """Handle ``mid convert``."""
    if args.file is None:
        _exit_arg("argument FILE is required")

    path = Path(args.file)

    # Validate path existence first — exit 2 for argument errors
    if not path.exists():
        _exit_arg(f"file not found: {path}")
    if not path.is_file():
        _exit_arg(f"not a file: {path}")

    # THEN resolve converter
    ext = path.suffix.lower()
    converter_cls = resolve_converter(ext)

    if converter_cls is None:
        _exit_fmt(f"unsupported format {ext}")

    from mid.converters.legacy import LegacyPlaceholder

    converter = converter_cls()
    is_legacy = isinstance(converter, LegacyPlaceholder)
    result = converter.convert(path)

    if not result.success:
        msg = result.error or "unknown error"
        if is_legacy:
            _exit_fmt(msg)
        _exit_conv(msg)

    if args.json:
        payload = {
            "content": result.content,
            "metadata": {
                "source": path.name,
                "format": ext.lstrip("."),
                "success": True,
            },
            "error": None,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.output:
        output_path = Path(args.output)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.content, encoding="utf-8")
        except OSError as exc:
            _exit_conv(f"could not write output file '{output_path}': {exc}")
    else:
        print(result.content)


# -- batch handler ---------------------------------------------------------


def handler_batch(args: argparse.Namespace) -> None:
    """Handle ``mid batch`` -- convert all supported files in a directory."""
    if args.input is None:
        _exit_arg("argument INPUT_DIR is required")

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        _exit_arg(f"not a directory: {args.input}")

    if args.output is None:
        _exit_arg("-o / --output is required for batch mode")

    output_dir = Path(args.output)

    # Pre-validate: output must not be an existing file
    if output_dir.exists() and not output_dir.is_dir():
        _exit_arg(f"output path exists and is not a directory: {output_dir}")

    # --recursive requires --preserve or --flatten to avoid silent overwrites
    if args.recursive and not args.preserve and not args.flatten:
        _exit_arg("--recursive requires --preserve or --flatten to prevent data loss")

    # --flatten without --recursive → error
    if args.flatten and not args.recursive:
        _exit_arg("--flatten requires --recursive")

    # --preserve requires --recursive (implied but check)
    if args.preserve and not args.recursive:
        _exit_arg("--preserve requires --recursive")

    # Discover files
    if args.recursive:
        all_entries = list(input_dir.rglob("*"))
    else:
        all_entries = list(input_dir.iterdir())

    files = [f for f in all_entries if f.is_file()]
    supported = [f for f in files if resolve_converter(f.suffix) is not None]
    skipped = len([f for f in files if resolve_converter(f.suffix) is None])

    processed = len(supported)
    succeeded = 0
    failed = 0

    output_dir.mkdir(parents=True, exist_ok=True)

    # Track used names for collision detection under --flatten
    used_names: set[str] = set()

    for file_path in supported:
        result = convert_file(file_path)

        if result.success:
            # Determine output path
            rel = file_path.relative_to(input_dir) if args.recursive else file_path
            if args.recursive and args.preserve:
                out = output_dir / rel.with_suffix(".md")
                out.parent.mkdir(parents=True, exist_ok=True)
            elif args.recursive and args.flatten:
                stem = file_path.stem
                out_name = f"{stem}.md"

                rel_parent = file_path.relative_to(input_dir).parent
                parent_prefix = "-".join(p for p in rel_parent.parts if p != ".")
                collision_index = 1

                while out_name in used_names or (output_dir / out_name).exists():
                    base_name = f"{parent_prefix}-{stem}" if parent_prefix else stem
                    if collision_index == 1:
                        out_name = f"{base_name}.md"
                    else:
                        out_name = f"{base_name}-{collision_index}.md"
                    collision_index += 1

                used_names.add(out_name)
                out = output_dir / out_name
            else:
                # Non-recursive: flat output (same name, .md extension)
                out_name = file_path.with_suffix(".md").name
                out = output_dir / out_name

            try:
                out.write_text(result.content, encoding="utf-8")
                succeeded += 1
            except OSError as exc:
                print(f"error: {file_path.name}: could not write output '{out}': {exc}", file=sys.stderr)
                failed += 1
        else:
            msg = result.error or "unknown error"
            print(f"error: {file_path.name}: {msg}", file=sys.stderr)
            failed += 1

    print(f"Processed: {processed}, Succeeded: {succeeded}, Failed: {failed}, Skipped: {skipped}")
    if failed:
        sys.exit(1)


# -- help handler ----------------------------------------------------------


def handler_help(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Handle ``mid help [topic]``."""
    if args.topic is None:
        parser.print_help()
        return

    # Find subparser by name
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, subparser in action.choices.items():
                if name == args.topic:
                    subparser.print_help()
                    return

    _exit_arg(f"unknown command '{args.topic}'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point (console_scripts / ``python -m mid``)."""
    parser = setup_parser()
    args = parser.parse_args()

    # --list-formats is a top-level flag (no subcommand needed)
    if args.list_formats:
        from mid.converters.legacy import LegacyPlaceholder

        supported = []
        legacy = []
        for ext, cls in sorted(REGISTRY.items()):
            if cls is LegacyPlaceholder:
                legacy.append(ext)
            else:
                supported.append(ext)
        print(f"Supported: {' '.join(supported)}")
        print(f"Legacy (migrate first): {' '.join(legacy)}")
        return

    # No subcommand → show help
    if args.command is None:
        parser.print_help()
        return

    # Dispatch
    if args.command == "help":
        handler_help(args, parser)
    elif args.command == "convert":
        handler_convert(args)
    elif args.command == "batch":
        handler_batch(args)
