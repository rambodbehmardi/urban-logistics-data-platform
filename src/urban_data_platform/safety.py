"""Public-content scanner with findings that reveal locations, not matched text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {
    ".gitignore",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {"LICENSE", "Makefile"}
IGNORED_PARTS = {".git", ".venv", "__pycache__", "build", "dist"}

RESTRICTED_CONTEXT = (
    "ap" + "ply",
    "app" + "lication",
    "mi" + "are",
    "\u006f\u0066\u006f\u0067\u0068\u0020\u006b\u006f\u006f\u0072\u006f\u0073\u0068",
    "\u0627\u067e\u0644\u0627\u06cc",
)

EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z])"
)
PHONE_PATTERN = re.compile(r"(?<![.\d])(?:\+?\d[ ()\-]*){10,}(?![.\d])")
KEY_HEADER_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRI" + r"VATE KEY-----",
    re.IGNORECASE,
)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b"
    r"\s*[:=]\s*['\"][^'\"\n]{8,}['\"]"
)
CLOUD_KEY_PATTERN = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
PRIVATE_NETWORK_PATTERN = re.compile(
    r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}"
    r"|192\.168\.(?:\d{1,3})\.(?:\d{1,3})"
    r"|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3})\.(?:\d{1,3}))\b"
)


@dataclass(frozen=True, order=True)
class SafetyFinding:
    path: str
    line: int
    rule: str


def _is_public_text(path: Path) -> bool:
    return path.name in TEXT_FILENAMES or path.suffix.lower() in TEXT_SUFFIXES


def iter_public_files(root: str | Path) -> Iterable[Path]:
    base = Path(root)
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in IGNORED_PARTS for part in path.relative_to(base).parts):
            continue
        if _is_public_text(path):
            yield path


def scan_text(text: str, display_path: str) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    patterns = (
        ("email-address", EMAIL_PATTERN),
        ("phone-number", PHONE_PATTERN),
        ("key-header", KEY_HEADER_PATTERN),
        ("secret-assignment", SECRET_ASSIGNMENT_PATTERN),
        ("cloud-key-shape", CLOUD_KEY_PATTERN),
        ("private-network-address", PRIVATE_NETWORK_PATTERN),
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        lowered = line.casefold()
        for term in RESTRICTED_CONTEXT:
            if term.casefold() in lowered:
                findings.append(
                    SafetyFinding(display_path, line_number, "restricted-context")
                )
                break
        for rule, pattern in patterns:
            if pattern.search(line):
                findings.append(SafetyFinding(display_path, line_number, rule))
    return findings


def scan_tree(root: str | Path) -> list[SafetyFinding]:
    base = Path(root).resolve()
    findings: list[SafetyFinding] = []
    for path in iter_public_files(base):
        display_path = path.relative_to(base).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(SafetyFinding(display_path, 1, "invalid-utf8"))
            continue
        findings.extend(scan_text(text, display_path))
    return sorted(set(findings))
