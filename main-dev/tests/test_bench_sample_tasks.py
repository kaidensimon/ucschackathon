import collections
import tempfile
import unittest
from pathlib import Path

from council.bench.graders import grade, load_tasks
from council.bench.sample_tasks import CATEGORIES, generate, main

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "bench" / "tasks" / "sample.jsonl"


class SampleTasksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "sample.jsonl"
        main(self.path)
        self.tasks = load_tasks(self.path)

    def test_file_in_repo_loads(self):
        self.assertTrue(SAMPLE.exists(), "run: python -m council.bench.sample_tasks")
        self.assertEqual(len(load_tasks(SAMPLE)), 48)

    def test_total_and_ids_unique(self):
        self.assertEqual(len(self.tasks), 48)
        self.assertEqual(len({t.id for t in self.tasks}), 48)

    def test_per_category_and_difficulty(self):
        by_cat = collections.Counter(t.category for t in self.tasks)
        self.assertEqual(set(by_cat), set(CATEGORIES))
        for c in CATEGORIES:
            self.assertEqual(by_cat[c], 6, c)
            diffs = collections.Counter(t.difficulty for t in self.tasks if t.category == c)
            self.assertEqual(diffs, {"easy": 2, "medium": 2, "hard": 2}, c)

    def test_answer_types_and_graders(self):
        for t in self.tasks:
            self.assertIn(t.answer_type, {"mcq", "numeric", "exact"}, t.id)
            self.assertEqual(t.grader["type"], {"mcq": "mcq", "exact": "exact",
                                                "numeric": "numeric_tolerance"}[t.answer_type], t.id)
            if t.answer_type == "mcq":
                self.assertIsNotNone(t.choices, t.id)
                self.assertGreaterEqual(len(t.choices), 2, t.id)
            else:
                self.assertIsNone(t.choices, t.id)

    def test_split_is_half_and_stratified(self):
        cal = [t for t in self.tasks if t.split == "calibration"]
        self.assertEqual(len(cal), 24)
        self.assertGreaterEqual(len(cal), 20)  # Tier B needs 20 usable tasks
        self.assertTrue(all(t.split in {"calibration", "test"} for t in self.tasks))
        for c in CATEGORIES:
            n = sum(1 for t in cal if t.category == c)
            self.assertEqual(n, 3, c)
            self.assertEqual(collections.Counter(t.difficulty for t in cal if t.category == c),
                             {"easy": 1, "medium": 1, "hard": 1}, c)

    def test_every_answer_grades_itself(self):
        for t in self.tasks:
            self.assertTrue(grade(t, t.answer), t.id)

    def test_generate_matches_file(self):
        rows = generate()
        self.assertEqual(len(rows), 48)
        self.assertEqual([r["id"] for r in rows], [t.id for t in self.tasks])

    def test_repo_file_matches_generator(self):
        if not SAMPLE.exists():
            self.skipTest("sample file not written yet")
        repo_tasks = load_tasks(SAMPLE)
        self.assertEqual([t.model_dump() for t in repo_tasks],
                         [t.model_dump() for t in self.tasks])


if __name__ == "__main__":
    unittest.main()
