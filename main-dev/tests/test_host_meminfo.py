"""Tests for council.host.meminfo. Run from the repo root: python -m unittest tests.test_host_meminfo -v"""

from __future__ import annotations

import os
import tempfile
import unittest

from council.host import meminfo

SAMPLE = """MemTotal:       134217728 kB
MemFree:         2097152 kB
MemAvailable:   120586240 kB
Buffers:          102400 kB
SwapTotal:       8388608 kB
SwapFree:        6291456 kB
HugePages_Total:       0
"""


class ParseMeminfoTests(unittest.TestCase):
    def test_parses_kb_values(self):
        info = meminfo.parse_meminfo(SAMPLE)
        self.assertEqual(info["MemTotal"], 134217728)
        self.assertEqual(info["MemAvailable"], 120586240)
        self.assertEqual(info["SwapFree"], 6291456)
        self.assertEqual(info["HugePages_Total"], 0)

    def test_skips_garbage_lines(self):
        info = meminfo.parse_meminfo("no colon here\nMemTotal: notanumber kB\nMemFree: 5 kB\n\n")
        self.assertNotIn("no colon here", info)
        self.assertNotIn("MemTotal", info)
        self.assertEqual(info, {"MemFree": 5})

    def test_empty_text(self):
        self.assertEqual(meminfo.parse_meminfo(""), {})


class ReadMeminfoTests(unittest.TestCase):
    def test_missing_file_gives_synthetic_128gib_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "no_such_meminfo")
            info = meminfo.read_meminfo(missing)
        self.assertEqual(info["MemTotal"], 128 * 1024 * 1024)
        self.assertAlmostEqual(meminfo.available_gib(info), 115.0)
        for key in ("MemAvailable", "SwapTotal", "SwapFree"):
            self.assertIn(key, info)

    def test_default_path_does_not_crash(self):
        info = meminfo.read_meminfo()
        self.assertIn("MemTotal", info)
        self.assertIn("MemAvailable", info)

    def test_reads_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "meminfo")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SAMPLE)
            info = meminfo.read_meminfo(path)
        self.assertEqual(info["MemAvailable"], 120586240)
        self.assertEqual(info["SwapTotal"], 8388608)


class GibHelpersTests(unittest.TestCase):
    def setUp(self):
        self.info = meminfo.parse_meminfo(SAMPLE)

    def test_available_gib(self):
        self.assertAlmostEqual(meminfo.available_gib(self.info), 120586240 / 1048576)

    def test_used_gib(self):
        expected = (134217728 - 120586240) / 1048576
        self.assertAlmostEqual(meminfo.used_gib(self.info), expected)

    def test_swap_used_gib(self):
        expected = (8388608 - 6291456) / 1048576
        self.assertAlmostEqual(meminfo.swap_used_gib(self.info), expected)
        self.assertAlmostEqual(meminfo.swap_used_gib(self.info), 2.0)

    def test_missing_keys_read_as_zero(self):
        self.assertEqual(meminfo.available_gib({}), 0.0)
        self.assertEqual(meminfo.used_gib({}), 0.0)
        self.assertEqual(meminfo.swap_used_gib({}), 0.0)

    def test_negative_values_clamp_to_zero(self):
        weird = {"MemTotal": 10, "MemAvailable": 20, "SwapTotal": 1, "SwapFree": 5}
        self.assertEqual(meminfo.used_gib(weird), 0.0)
        self.assertEqual(meminfo.swap_used_gib(weird), 0.0)


if __name__ == "__main__":
    unittest.main()
