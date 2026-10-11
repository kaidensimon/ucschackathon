import unittest

from council.core.schemas import CalibrationCell
from council.router.tier_b import CalibrationIndex


def cell(t, m, ok, key):
    return CalibrationCell(task_id=t, model_id=m, correct=ok, answer_key=key)


class FakeStore:
    def __init__(self, matrix):
        self._m = matrix

    def calibration_matrix(self):
        return self._m


def build(n=6):
    matrix, emb = {}, {}
    for i in range(n):
        t = f"t{i}"
        emb[t] = [1.0, float(i) * 0.1]
        matrix[t] = {
            "a": cell(t, "a", True, "X"),
            "b": cell(t, "b", i % 2 == 0, "X" if i % 2 == 0 else "Y"),
            "c": cell(t, "c", i % 2 == 1, "X" if i % 2 == 1 else "Z"),
        }
    return matrix, emb


class TierBTest(unittest.TestCase):
    def test_ready(self):
        m, e = build(6)
        idx = CalibrationIndex(m, e, {})
        self.assertTrue(idx.ready(5))
        self.assertFalse(idx.ready(20))

    def test_neighbours_format_and_weights(self):
        m, e = build(6)
        idx = CalibrationIndex.from_store(FakeStore(m), e)
        nb = idx.neighbours([1.0, 0.0], k=4)
        self.assertEqual(len(nb), 4)
        self.assertAlmostEqual(sum(n["weight"] for n in nb), 1.0)
        self.assertEqual(nb[0]["truth"], "X")
        self.assertEqual(set(nb[0]["answers"]), {"a", "b", "c"})

    def test_negative_cosine_clipped(self):
        m = {"t": {"a": cell("t", "a", True, "X")}}
        idx = CalibrationIndex(m, {"t": [-1.0, 0.0]}, {"t": "X"})
        nb = idx.neighbours([1.0, 0.0])
        self.assertEqual(nb[0]["weight"], 0.0)

    def test_q_b(self):
        m, e = build(6)
        idx = CalibrationIndex(m, e, {})
        self.assertGreater(idx.q_b("a", [1.0, 0.0], 0.5), 0.5)
        self.assertEqual(idx.q_b("nobody", [1.0, 0.0], 0.42), 0.42)

    def test_error_distances(self):
        m, e = build(6)
        idx = CalibrationIndex(m, e, {})
        d = idx.error_distances(["a", "b", "c"])
        self.assertEqual(d[("b", "c")], d[("c", "b")])
        self.assertAlmostEqual(d[("b", "c")], 1.0)  # perfectly anti-correlated
        self.assertEqual(d[("a", "b")], 0.5)  # a never wrong: constant


if __name__ == "__main__":
    unittest.main()
