import re
import unittest
from pathlib import Path

from council.bench.graders import grade, load_tasks, normalize
from council.core.schemas import BenchTask
from council.probe.dataset import (
    Pair,
    make_pairs,
    near_int,
    near_number,
    qa_text,
    split_by_task,
    statement_pairs,
)

SAMPLE = Path(__file__).resolve().parents[1] / "bench" / "tasks" / "sample.jsonl"
INSTRUCTION = re.compile(r"\b(lie|lying|false|falsely|deceive|pretend|wrong|incorrect|untrue)\b", re.I)


def mcq(i, answer="B", cat="logic"):
    return BenchTask(id=f"m{i}", prompt=f"Pick {i}?\nA) one\nB) two\nC) three", category=cat,
                     choices=["A one", "B two", "C three"], answer_type="mcq", answer=answer)


def num(i, answer, cat="math"):
    return BenchTask(id=f"n{i}", prompt=f"Count {i}?", category=cat, answer_type="numeric",
                     answer=answer)


def exact(i, answer, cat="knowledge"):
    return BenchTask(id=f"e{i}", prompt=f"Name {i}?", category=cat, answer_type="exact",
                     answer=answer)


class MakePairsTests(unittest.TestCase):
    def test_template_is_the_same_on_both_sides(self):
        tasks = [mcq(1), num(1, "391"), exact(1, "canberra"), exact(2, "gold")]
        pairs = make_pairs(tasks, 0)
        self.assertEqual([p.task_id for p in pairs], ["m1", "n1", "e1", "e2"])
        by_id = {t.id: t for t in tasks}
        for p in pairs:
            t = by_id[p.task_id]
            self.assertIsInstance(p, Pair)
            self.assertEqual(p.category, t.category)
            self.assertEqual(p.honest_text, f"Question: {t.prompt}\nAnswer: {p.truth}")
            self.assertEqual(p.lie_text, f"Question: {t.prompt}\nAnswer: {p.false_answer}")
            self.assertNotEqual(p.truth, p.false_answer)
            self.assertEqual(p.honest_text, qa_text(t.prompt, p.truth))

    def test_truth_is_right_and_lie_is_wrong_for_the_grader(self):
        tasks = load_tasks(SAMPLE)
        pairs = make_pairs(tasks, 3)
        by_id = {t.id: t for t in tasks}
        self.assertGreaterEqual(len(pairs), 40)
        for p in pairs:
            t = by_id[p.task_id]
            self.assertTrue(grade(t, p.truth), p)
            self.assertFalse(grade(t, p.false_answer), p)

    def test_no_instruction_word_is_added(self):
        for p in make_pairs(load_tasks(SAMPLE), 1) + statement_pairs(1, 120):
            for text in (p.honest_text, p.lie_text):
                self.assertIsNone(INSTRUCTION.search(text), text)

    def test_mcq_lie_is_another_choice_with_its_text(self):
        seen = set()
        for seed in range(12):
            p = make_pairs([mcq(1)], seed)[0]
            self.assertEqual(p.truth, "B two")
            self.assertIn(p.false_answer, ("A one", "C three"))
            seen.add(p.false_answer)
        self.assertEqual(seen, {"A one", "C three"})

    def test_mcq_without_choice_letters_or_choices(self):
        t = BenchTask(id="x", prompt="p", choices=["red", "blue"], answer_type="mcq", answer="A")
        p = make_pairs([t], 0)[0]
        self.assertEqual((p.truth, p.false_answer), ("A red", "B blue"))
        bare = BenchTask(id="y", prompt="p", answer_type="mcq", answer="D")
        p = make_pairs([bare], 0)[0]
        self.assertEqual(p.truth, "D")
        self.assertIn(p.false_answer, ("A", "B", "C"))

    def test_numeric_lie_is_near_and_not_always_plus_one(self):
        deltas = set()
        for seed in range(30):
            p = make_pairs([num(1, "391")], seed)[0]
            d = int(p.false_answer) - 391
            self.assertNotEqual(d, 0)
            self.assertLessEqual(abs(d), 59)
            self.assertEqual(len(p.false_answer), 3)  # same digit count: same length pattern
            deltas.add(d)
        self.assertGreater(len(deltas), 5)
        self.assertTrue(any(d < 0 for d in deltas))

    def test_near_number_keeps_the_format(self):
        import random
        rng = random.Random(0)
        for _ in range(50):
            self.assertGreaterEqual(near_int(0, rng), 1)
            self.assertGreaterEqual(near_int(2, rng), 0)
            got = near_number("3.14", rng)
            self.assertRegex(got, r"^\d+\.\d\d$")
            self.assertNotEqual(got, "3.14")
        self.assertIsNone(near_number("three", rng))
        self.assertLess(int(near_number("-40", rng)), 0 + 20)

    def test_exact_lie_comes_from_the_same_category(self):
        tasks = [exact(1, "canberra"), exact(2, "gold"), exact(3, "jupiter"),
                 exact(4, "mice", "writing"), exact(5, "simile", "writing")]
        pairs = {p.task_id: p for p in make_pairs(tasks, 5)}
        know = {"canberra", "gold", "jupiter"}
        for tid in ("e1", "e2", "e3"):
            self.assertIn(pairs[tid].false_answer, know - {pairs[tid].truth})
        # every answer is used once as a lie: lies have the lengths of the truths
        self.assertEqual({pairs[t].false_answer for t in ("e1", "e2", "e3")}, know)
        self.assertEqual(pairs["e4"].false_answer, "simile")
        self.assertEqual(pairs["e5"].false_answer, "mice")

    def test_exact_alone_in_its_category_borrows_or_is_left_out(self):
        pairs = make_pairs([exact(1, "gold"), exact(2, "mice", "writing")], 0)
        self.assertEqual({p.task_id: p.false_answer for p in pairs}, {"e1": "mice", "e2": "gold"})
        self.assertEqual(make_pairs([exact(1, "gold")], 0), [])
        same = make_pairs([exact(1, "Gold"), exact(2, "gold.")], 0)
        self.assertEqual(same, [])  # the only other answer means the same

    def test_tasks_without_a_usable_answer_are_left_out(self):
        tasks = [BenchTask(id="f", prompt="p", answer_type="freeform", answer="x"),
                 BenchTask(id="c", prompt="p", answer_type="code", answer="assert 1"),
                 num(1, ""), mcq(2, answer="Z"), num(3, "7"), num(3, "8")]
        self.assertEqual([p.task_id for p in make_pairs(tasks, 0)], ["n3"])

    def test_deterministic_per_seed(self):
        tasks = load_tasks(SAMPLE)
        self.assertEqual(make_pairs(tasks, 4), make_pairs(tasks, 4))
        self.assertNotEqual(make_pairs(tasks, 4), make_pairs(tasks, 5))

    def test_answer_lengths_are_balanced_over_the_sample(self):
        pairs = make_pairs(load_tasks(SAMPLE), 0)
        honest = sum(len(p.truth) for p in pairs) / len(pairs)
        lie = sum(len(p.false_answer) for p in pairs) / len(pairs)
        self.assertLess(abs(honest - lie), 1.0)


class SplitTests(unittest.TestCase):
    def test_no_question_on_both_sides(self):
        pairs = statement_pairs(0, 50)
        train, test = split_by_task(pairs, 0.3, 7)
        self.assertEqual(len(test), 15)
        self.assertEqual(len(train), 35)
        self.assertFalse({p.task_id for p in train} & {p.task_id for p in test})
        self.assertEqual(split_by_task(pairs, 0.3, 7), (train, test))
        self.assertNotEqual(split_by_task(pairs, 0.3, 8)[1], test)

    def test_repeated_task_id_stays_on_one_side(self):
        a = Pair("t1", "math", "h", "l", "1", "2")
        b = Pair("t1", "math", "h2", "l2", "1", "3")
        c = Pair("t2", "math", "h3", "l3", "1", "4")
        for seed in range(6):
            train, test = split_by_task([a, b, c], 0.5, seed)
            self.assertFalse({p.task_id for p in train} & {p.task_id for p in test})
            self.assertTrue(train and test)

    def test_small_inputs(self):
        self.assertEqual(split_by_task([], 0.3, 0), ([], []))
        one = [Pair("t", "math", "h", "l", "1", "2")]
        self.assertEqual(split_by_task(one, 0.3, 0), (one, []))


class StatementTests(unittest.TestCase):
    def test_count_unique_and_deterministic(self):
        pairs = statement_pairs(0, 200)
        self.assertEqual(len(pairs), 200)
        self.assertEqual(len({p.task_id for p in pairs}), 200)
        self.assertEqual(pairs, statement_pairs(0, 200))
        self.assertNotEqual(pairs, statement_pairs(1, 200))
        self.assertEqual(statement_pairs(0, 0), [])
        self.assertEqual(len(statement_pairs(2, 500)), 500)

    def test_all_four_kinds_and_same_frame(self):
        pairs = statement_pairs(0, 80)
        kinds = {p.task_id.split("-")[1] for p in pairs}
        self.assertEqual(kinds, {"capital", "arith", "unit", "order"})
        for p in pairs:
            self.assertNotEqual(p.honest_text, p.lie_text)
            if p.task_id.split("-")[1] != "capital":  # a capital may be two words
                self.assertEqual(len(p.honest_text.split()), len(p.lie_text.split()))
            self.assertTrue(p.honest_text.endswith(".") and p.lie_text.endswith("."))

    def test_statements_are_really_true_and_false(self):
        from council.probe.dataset import CAPITALS, MONTHS
        caps = dict(CAPITALS)
        for p in statement_pairs(3, 300):
            kind = p.task_id.split("-")[1]
            if kind == "arith":
                expr, shown = p.honest_text.rstrip(".").split(" = ")
                self.assertEqual(eval(expr), int(shown), p)  # digits and + - * only
                self.assertNotEqual(eval(expr), int(p.lie_text.rstrip(".").split(" = ")[1]), p)
            elif kind == "capital":
                country = p.honest_text[len("The capital of "):].split(" is ")[0]
                self.assertEqual(caps[country], p.truth)
                self.assertNotEqual(caps[country], p.false_answer)
                self.assertIn(p.false_answer, caps.values())
            elif kind == "unit":
                self.assertNotEqual(normalize(p.truth, "numeric"), normalize(p.false_answer, "numeric"))
            else:
                words = p.honest_text.rstrip(".").split()
                if words[0] == "In":
                    a, b = MONTHS.index(words[4]), MONTHS.index(words[-1])
                    self.assertTrue(a < b if "before" in words else a > b, p)
                else:
                    a, b = int(words[0]), int(words[-1])
                    self.assertTrue(a > b if words[2] == "greater" else a < b, p)


if __name__ == "__main__":
    unittest.main()
