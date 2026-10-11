import unittest

from council.chamber.cruxes import build_cruxes_call, heuristic_cruxes, parse_cruxes
from council.core.schemas import Critique, Flaw, Option, Review


def _opts():
    return [Option(id="o1", summary="A", holders=[1]), Option(id="o2", summary="B", holders=[2])]


def _crit():
    return {
        1: Critique(reviews=[Review(target="B", flaws=[
            Flaw(id="f1", text="wrong sum", severity="fatal", kind="factual"),
            Flaw(id="f2", text="nit", severity="minor"),
            Flaw(id="f3", text="too pricey", severity="major", kind="preference"),
        ])]),
        2: Critique(reviews=[Review(target="A", flaws=[
            Flaw(id="f1", text="Wrong sum", severity="major", kind="logic"),
            Flaw(id="f2", text="slow", severity="major", kind="logic"),
        ])]),
    }


class CruxTests(unittest.TestCase):
    def test_build(self):
        c = build_cruxes_call("r1", "clerk", _opts(), _crit(), max_cruxes=3)
        self.assertEqual(c.purpose, "clerk.extract_cruxes")
        self.assertEqual(c.model_id, "clerk")
        self.assertIn("at most 3", c.messages[-1]["content"])
        enum = c.json_schema["properties"]["cruxes"]["items"]["properties"]["between"]["items"]["enum"]
        self.assertEqual(enum, ["o1", "o2"])

    def test_parse_ok_and_drop(self):
        p = {"cruxes": [
            {"statement": "s1", "between": ["o1", "o2"], "kind": "value"},
            {"statement": "bad", "between": ["o1", "o9"], "kind": "factual"},
            {"statement": "s3", "between": ["o2"], "kind": "weird"},
        ]}
        r = parse_cruxes(p, _opts())
        self.assertEqual([c.id for c in r], ["x1", "x2"])
        self.assertEqual(r[0].kind, "value")
        self.assertEqual(r[1].kind, "factual")

    def test_parse_cap_and_bad(self):
        p = {"cruxes": [{"statement": f"s{i}", "between": ["o1"], "kind": "factual"} for i in range(9)]}
        self.assertEqual(len(parse_cruxes(p, _opts())), 5)
        self.assertEqual(len(parse_cruxes(p, _opts(), max_cruxes=2)), 2)
        self.assertEqual(parse_cruxes(None, _opts()), [])
        self.assertEqual(parse_cruxes({"cruxes": "x"}, _opts()), [])

    def test_heuristic(self):
        r = heuristic_cruxes(_opts(), _crit())
        self.assertEqual([c.statement for c in r], ["wrong sum", "too pricey", "slow"])
        self.assertEqual([c.kind for c in r], ["factual", "value", "checkable"])
        self.assertEqual(r[0].between, ["o1", "o2"])
        self.assertEqual(r[0].id, "x1")

    def test_heuristic_empty(self):
        self.assertEqual(heuristic_cruxes(_opts(), {}), [])
        self.assertEqual(heuristic_cruxes(_opts()[:1], _crit()), [])


if __name__ == "__main__":
    unittest.main()
