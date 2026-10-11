import os
import tempfile
import unittest
from pathlib import Path

from council.works.brief import brief_hash, build_brief


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def w(self, rel, text="x\n", data=None):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if data is not None:
            p.write_bytes(data)
        else:
            p.write_text(text, encoding="utf-8")
        return p

    def test_empty_and_missing(self):
        self.assertEqual(build_brief(self.root), "(empty workspace)")
        self.assertEqual(build_brief(self.root / "nope"), "(empty workspace)")

    def test_tree_langs_head_skips(self):
        self.w("README.md", "\n".join(f"line{i}" for i in range(100)))
        self.w("src/main.py", "print(1)\n")
        self.w("node_modules/x.js")
        self.w(".git/config")
        self.w("pic.png", data=b"\x89PNG\x00")
        b = build_brief(self.root)
        self.assertIn("Python (1)", b)
        self.assertIn("src/main.py", b)
        self.assertIn("line39", b)
        self.assertNotIn("line40", b)
        self.assertNotIn("node_modules", b)
        self.assertNotIn(".git", b)
        self.assertNotIn("pic.png", b)

    def test_max_chars(self):
        for i in range(200):
            self.w(f"f{i}.py", "a\n")
        self.assertLessEqual(len(build_brief(self.root, max_chars=500)), 500)

    def test_max_files(self):
        for i in range(20):
            self.w(f"f{i:02}.py")
        b = build_brief(self.root, max_files=5)
        self.assertIn("f04.py", b)
        self.assertNotIn("f05.py", b)

    def test_hash(self):
        p = self.w("a.py", "1")
        h1 = brief_hash(self.root)
        self.assertEqual(h1, brief_hash(self.root))
        p.write_text("22", encoding="utf-8")
        self.assertNotEqual(h1, brief_hash(self.root))
        h2 = brief_hash(self.root)
        self.w("node_modules/z.js")
        self.assertEqual(h2, brief_hash(self.root))
        self.assertIsInstance(brief_hash(self.root / "nope"), str)


if __name__ == "__main__":
    unittest.main()
