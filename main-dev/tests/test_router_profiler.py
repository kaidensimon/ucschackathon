import unittest

from council.core.schemas import CATEGORIES, CallSpec, TaskProfile
from council.router import profiler as p


class ProfilerTests(unittest.TestCase):
    def test_heuristic_basic(self):
        pr = p.heuristic_profile("Implement a python function and build the files for a parser")
        self.assertEqual(pr.deliverable, "build")
        self.assertAlmostEqual(sum(pr.categories.values()), 1.0)
        self.assertEqual(max(pr.categories, key=pr.categories.get), "code")

    def test_empty_never_empty(self):
        pr = p.heuristic_profile("")
        self.assertTrue(pr.categories)
        self.assertAlmostEqual(sum(pr.categories.values()), 1.0)
        self.assertEqual(pr.deliverable, "answer")

    def test_needs_and_plan(self):
        pr = p.heuristic_profile("Look at this screenshot and design the architecture")
        self.assertIn("vision", pr.needs)
        self.assertEqual(pr.deliverable, "plan")

    def test_difficulty(self):
        self.assertEqual(p.heuristic_profile("simple quick thing").difficulty, "easy")
        long_task = "prove this complex theorem " + "word " * 250
        self.assertEqual(p.heuristic_profile(long_task).difficulty, "hard")

    def test_cosine(self):
        self.assertAlmostEqual(p.cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(p.cosine([1, 0], [0, 1]), 0.0)
        self.assertEqual(p.cosine([], [1]), 0.0)
        self.assertEqual(p.cosine([0, 0], [1, 1]), 0.0)

    def test_knn_and_neighbours(self):
        cal = [
            {"embedding": [1, 0], "category": "math", "difficulty": "hard"},
            {"embedding": [0.9, 0.1], "category": "math", "difficulty": "hard"},
            {"embedding": [0, 1], "category": "writing", "difficulty": "easy"},
        ]
        n = p.knn([1, 0], cal, k=2)
        self.assertEqual(len(n), 2)
        self.assertGreaterEqual(n[0][0], n[1][0])
        out = p.profile_from_neighbours(n)
        self.assertEqual(out["categories"], {"math": 1.0})
        self.assertEqual(out["difficulty"], "hard")

    def test_build_call(self):
        c = p.build_profile_call("r1", "clerk", "do x", "brief")
        self.assertIsInstance(c, CallSpec)
        self.assertEqual(c.purpose, "profile")
        for key in ("needs", "deliverable", "categories"):
            self.assertIn(key, c.json_schema["properties"])

    def test_merge(self):
        h = p.heuristic_profile("write an essay")
        clerk = {"categories": {"writing": 1.0}, "needs": ["multilingual"], "deliverable": "plan"}
        neigh = {"categories": {"reading": 1.0}, "difficulty": "hard"}
        m = p.merge_profiles(h, clerk, neigh)
        self.assertIsInstance(m, TaskProfile)
        self.assertAlmostEqual(m.categories["writing"], 0.5)
        self.assertAlmostEqual(m.categories["reading"], 0.5)
        self.assertEqual(m.deliverable, "plan")
        self.assertIn("multilingual", m.needs)
        only = p.merge_profiles(h, None, None)
        self.assertEqual(only.categories, h.categories)
        for c in m.categories:
            self.assertIn(c, CATEGORIES)


if __name__ == "__main__":
    unittest.main()
