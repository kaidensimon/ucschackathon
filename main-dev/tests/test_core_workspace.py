"""Tests for council/core/workspace.py (spec 27, 28)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from council.core import workspace as ws


class ProjectIdTests(unittest.TestCase):
    def test_length_and_hex(self) -> None:
        pid = ws.project_id(tempfile.gettempdir())
        self.assertEqual(len(pid), 12)
        int(pid, 16)

    def test_stable(self) -> None:
        d = tempfile.gettempdir()
        self.assertEqual(ws.project_id(d), ws.project_id(d))

    def test_str_and_path_agree(self) -> None:
        d = Path(tempfile.gettempdir())
        self.assertEqual(ws.project_id(d), ws.project_id(str(d)))

    def test_relative_and_absolute_agree(self) -> None:
        here = Path(".").resolve()
        self.assertEqual(ws.project_id("."), ws.project_id(here))

    def test_different_paths_differ(self) -> None:
        a = Path(tempfile.gettempdir()) / "alpha_ws"
        b = Path(tempfile.gettempdir()) / "beta_ws"
        self.assertNotEqual(ws.project_id(a), ws.project_id(b))

    def test_case_normalized(self) -> None:
        base = str(Path(tempfile.gettempdir()).resolve())
        self.assertEqual(ws.project_id(base.upper()), ws.project_id(base.lower()))

    def test_scope_for(self) -> None:
        d = tempfile.gettempdir()
        self.assertEqual(ws.scope_for(d), "project:" + ws.project_id(d))


class SafeNameTests(unittest.TestCase):
    def assert_folder_safe(self, name: str) -> None:
        self.assertTrue(name)
        self.assertNotIn(name, (".", ".."))
        self.assertRegex(name, r"^[A-Za-z0-9._-]+$")
        self.assertLessEqual(len(name), 120)

    def test_plain_id_unchanged(self) -> None:
        self.assertEqual(ws.safe_name("qwen2.5-coder_7b"), "qwen2.5-coder_7b")

    def test_slashes_and_colons_replaced(self) -> None:
        name = ws.safe_name("library/llama3:8b")
        self.assert_folder_safe(name)
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)

    def test_no_collision(self) -> None:
        self.assertNotEqual(ws.safe_name("a/b"), ws.safe_name("a_b"))

    def test_deterministic(self) -> None:
        self.assertEqual(ws.safe_name("x:y z"), ws.safe_name("x:y z"))

    def test_empty_and_dots(self) -> None:
        for raw in ("", ".", "..", "///", "..."):
            self.assert_folder_safe(ws.safe_name(raw))

    def test_windows_reserved(self) -> None:
        for raw in ("CON", "nul", "com1", "LPT9"):
            name = ws.safe_name(raw)
            self.assert_folder_safe(name)
            self.assertNotIn(name.casefold(), {"con", "nul", "com1", "lpt9"})

    def test_long_capped(self) -> None:
        name = ws.safe_name("m" * 500 + "/")
        self.assert_folder_safe(name)

    def test_non_str_raises(self) -> None:
        with self.assertRaises(TypeError):
            ws.safe_name(None)  # type: ignore[arg-type]


class PathTests(unittest.TestCase):
    def test_adapters_dir(self) -> None:
        home = Path("H")
        got = ws.adapters_dir(home, "abc123def456", "org/model:1b")
        self.assertEqual(got, home / "adapters" / "abc123def456" / ws.safe_name("org/model:1b"))

    def test_runs_dir(self) -> None:
        home = Path("H")
        self.assertEqual(ws.runs_dir(home, "run_1"), home / "runs" / "run_1")

    def test_accepts_str_home(self) -> None:
        self.assertIsInstance(ws.runs_dir("H", "r"), Path)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
