#!/usr/bin/env python3
"""Run the repository public-content guard."""

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from urban_data_platform.safety import scan_tree  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else REPOSITORY_ROOT
    findings = scan_tree(target)
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.rule}")
        print(f"public safety scan failed with {len(findings)} finding(s)")
        return 1
    print("public safety scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
