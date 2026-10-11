import json
import tempfile
import unittest
from pathlib import Path

from council.chronicle.corrections import CorrectionBook, build_correction, adapters_dir
from council.core.schemas import ModelEntry, TribunalOutcome
from council.core.store import Store


def make(book_task="parse the config file", lesson="Check the config schema first.", wrong="use regex", mid="m1"):
    out = TribunalOutcome(outcome="failed", error_kind="logic", lesson=lesson)
    return build_correction(out, "proj", ModelEntry(id=mid, lineage="L"), "r1", book_task,
                            wrong, "use a parser", "agreement", 100.0)


class CorrectionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(":memory:")
        self.book = CorrectionBook(self.store, Path(self.tmp.name))

    def test_build(self):
        c = make()
        self.assertEqual((c.project, c.model_id, c.lineage, c.verified_by), ("proj", "m1", "L", "agreement"))
        self.assertEqual(len(c.examples), 2)
        a, b = c.examples
        self.assertEqual(a.messages, [{"role": "user", "content": "parse the config file"}])
        self.assertIn("use a parser", a.target)
        self.assertIn("Check the config schema first.", a.target)
        self.assertIn("A colleague proposes: use regex. Is that right?", b.messages[0]["content"])
        self.assertIn("use a parser", b.target)

    def test_record_and_size(self):
        p = self.book.record(make())
        self.assertEqual(p, adapters_dir(Path(self.tmp.name), "proj", "m1") / "dataset.jsonl")
        self.assertEqual(self.book.dataset_size("proj", "m1"), 2)
        self.book.record(make())
        self.assertEqual(self.book.dataset_size("proj", "m1"), 4)
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(set(rows[0]), {"messages", "target"})
        self.assertEqual(len(self.store.corrections_list("proj", "m1")), 4 // 2)
        self.assertEqual(self.book.dataset_size("proj", "nope"), 0)

    def test_notes(self):
        self.assertEqual(self.book.notes_for("proj", "m1", "config"), "")
        self.book.record(make())
        self.book.record(make(book_task="sort numbers", lesson="Sort stably.", wrong="bubble"))
        n = self.book.notes_for("proj", "m1", "how to parse a config")
        self.assertTrue(n.startswith("Corrections from earlier sessions in this project:\n- "))
        self.assertIn("- Check the config schema first.", n)
        self.assertNotIn("Sort stably", n)
        self.assertEqual(self.book.notes_for("proj", "m1", "zzzz qqqq"), "")
        self.assertEqual(self.book.notes_for("other", "m1", "config"), "")
        self.assertEqual(self.book.notes_for("proj", "m2", "config"), "")
        both = self.book.notes_for("proj", "m1", "")
        self.assertIn("Sort stably", both)
        self.assertEqual(len(self.book.notes_for("proj", "m1", "", k=1).splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
