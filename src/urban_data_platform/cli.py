"""Command-line interface for generation, loading, inspection, and cleanup."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from .contracts import ContractViolation
from .generate import generate_batches
from .pipeline import get_summary, run_pipeline


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _safe_clean(output_dir: str | Path) -> bool:
    target = Path(output_dir)
    if target.name != "build":
        raise ValueError("clean only accepts a directory whose final component is 'build'")
    if target.is_symlink():
        raise ValueError("clean refuses symbolic-link targets")
    if not target.exists():
        return False
    if not target.is_dir():
        raise ValueError("clean target exists and is not a directory")
    shutil.rmtree(target)
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urban-data-platform",
        description="Run a deterministic synthetic logistics data pipeline.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="write deterministic JSONL batches")
    generate.add_argument("--output-dir", type=Path, default=Path("build/raw"))
    generate.add_argument("--seed", type=int, default=734_021)

    run = commands.add_parser("run", help="ingest batches and rebuild derived tables")
    run.add_argument("--db", type=Path, default=Path("build/platform.db"))
    run.add_argument("--input", type=Path, nargs="+", required=True)
    run.add_argument("--reset", action="store_true")

    summary = commands.add_parser("summary", help="print validated database metrics")
    summary.add_argument("--db", type=Path, default=Path("build/platform.db"))

    demo = commands.add_parser("demo", help="run the complete two-batch scenario")
    demo.add_argument("--output-dir", type=Path, default=Path("build/raw"))
    demo.add_argument("--db", type=Path, default=Path("build/platform.db"))
    demo.add_argument("--seed", type=int, default=734_021)
    demo.add_argument("--reset", action="store_true")

    clean = commands.add_parser("clean", help="remove generated build artifacts")
    clean.add_argument("--output-dir", type=Path, default=Path("build"))
    return parser


def _run_command(arguments: argparse.Namespace) -> int:
    if arguments.command == "generate":
        paths = generate_batches(arguments.output_dir, arguments.seed)
        _print_json({name: str(path) for name, path in paths.items()})
        return 0

    if arguments.command == "run":
        _print_json(run_pipeline(arguments.db, arguments.input, reset=arguments.reset))
        return 0

    if arguments.command == "summary":
        if not arguments.db.is_file():
            raise ValueError("database file does not exist")
        _print_json(get_summary(arguments.db))
        return 0

    if arguments.command == "demo":
        paths = generate_batches(arguments.output_dir, arguments.seed)
        initial = run_pipeline(arguments.db, [paths["initial"]], reset=arguments.reset)
        final = run_pipeline(arguments.db, [paths["late"]])
        _print_json(
            {
                "final": final,
                "initial_open_outcomes": initial["open_outcomes"],
                "late_batch_reduced_open_outcomes": (
                    final["open_outcomes"] < initial["open_outcomes"]
                ),
            }
        )
        return 0

    if arguments.command == "clean":
        removed = _safe_clean(arguments.output_dir)
        _print_json({"removed": removed, "target": str(arguments.output_dir)})
        return 0

    raise ValueError("unknown command")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        return _run_command(arguments)
    except (ContractViolation, OSError, sqlite3.Error, ValueError) as exc:
        parser.error(str(exc))
    return 2
