from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from urban_data_platform.safety import scan_text, scan_tree


class SafetyScanTestCase(unittest.TestCase):
    def test_repository_passes_its_own_scan(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        self.assertEqual(scan_tree(repository_root), [])

    def test_restricted_context_is_reported_without_matched_text(self) -> None:
        restricted = "ap" + "ply"
        findings = scan_text(f"public wording: {restricted}\n", "sample.md")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "sample.md")
        self.assertEqual(findings[0].line, 1)
        self.assertEqual(findings[0].rule, "restricted-context")
        self.assertFalse(hasattr(findings[0], "matched_text"))

    def test_contact_and_secret_shapes_are_detected(self) -> None:
        address = "person" + chr(64) + "sample.test"
        secret_name = "access" + "_" + "token"
        text = f"{address}\n{secret_name} = {'x' * 12!r}\n"
        rules = {finding.rule for finding in scan_text(text, "fixture.txt")}
        self.assertEqual(rules, {"email-address", "secret-assignment"})

    def test_generated_build_directory_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "build" / "record.txt"
            generated.parent.mkdir(parents=True)
            generated.write_text("ap" + "ply", encoding="utf-8")
            self.assertEqual(scan_tree(root), [])


if __name__ == "__main__":
    unittest.main()
