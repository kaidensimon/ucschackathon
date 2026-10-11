import unittest

from council.chamber.outlier import examiners, find_outlier, seat_distance
from council.core.schemas import Ballot, SeatAssignment


def B(choice, ranking, conf=0.5, block=None):
    return Ballot(choice=choice, ranking=ranking, confidence=conf, blocking_objection=block)


class OutlierTests(unittest.TestCase):
    def test_chose_it(self):
        self.assertEqual(seat_distance(B("a", ["a", "b"]), "a", "a", 2), 0.0)

    def test_formula(self):
        b = B("c", ["c", "b", "a"], conf=0.4, block="no")
        self.assertAlmostEqual(seat_distance(b, None, "a", 3), 1.0 + 0.5 + 0.1)
        b = B("b", ["b", "a", "c"], conf=0.0)
        self.assertAlmostEqual(seat_distance(b, None, "a", 3), 0.5)

    def test_no_ballot(self):
        self.assertEqual(seat_distance(None, "b", "a", 3), 1.0)
        self.assertEqual(seat_distance(None, "a", "a", 3), 0.0)
        self.assertEqual(seat_distance(None, None, "a", 3), 0.0)

    def test_find(self):
        fb = {1: B("a", ["a", "b"]), 2: B("b", ["b", "a"], 0.9), 3: None}
        self.assertEqual(find_outlier(fb, {1: "a", 2: "b", 3: "a"}, "a", 2), 2)
        self.assertIsNone(find_outlier({1: B("a", ["a"])}, {1: "a"}, "a", 1))

    def test_ties(self):
        fb = {1: B("b", ["b", "a"], 0.5), 2: B("b", ["b", "a"], 0.5), 3: B("b", ["b", "a"], 0.8)}
        self.assertEqual(find_outlier(fb, {}, "a", 2), 3)
        del fb[3]
        self.assertEqual(find_outlier(fb, {}, "a", 2), 1)

    def test_examiners(self):
        seats = [SeatAssignment(seat_no=i, model_id="m", q=q) for i, q in
                 [(1, 0.5), (2, 0.9), (3, 0.7), (4, 0.8)]]
        fb = {1: B("a", ["a"]), 2: B("a", ["a"]), 3: B("a", ["a"]), 4: B("b", ["b"])}
        self.assertEqual(examiners(seats, 4, fb, "a", 2), [2, 3])
        self.assertEqual(examiners(seats, 4, {}, "a", 2), [2, 3])


if __name__ == "__main__":
    unittest.main()
