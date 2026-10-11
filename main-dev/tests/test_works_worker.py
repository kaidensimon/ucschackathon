import json
import unittest

from council.core.schemas import (
    CallResult,
    Check,
    CheckResult,
    InterfaceDef,
    MicroTask,
    TaskBudget,
)
from council.works.worker import attempt_plan, build_worker_call, feedback_text, parse_output


def _task():
    return MicroTask(
        id="t1",
        goal="make add",
        write_set=["a.py"],
        acceptance=[Check(type="exists", path="a.py")],
        budget=TaskBudget(max_output_tokens=777),
    )


class WorkerTest(unittest.TestCase):
    def test_plan(self):
        self.assertEqual(attempt_plan(1, "w", "s"), ("w", 0.2))
        self.assertEqual(attempt_plan(2, "w", "s"), ("w", 0.6))
        self.assertEqual(attempt_plan(3, "w", "s"), ("s", 0.2))
        self.assertEqual(attempt_plan(3, "w", None), ("w", 0.2))

    def test_build(self):
        spec = build_worker_call("r", _task(), 2, "w", 0.6, "bad thing", "prev out",
                                 [InterfaceDef(name="add", definition="def add(a,b)")])
        self.assertEqual(spec.call_id, "r:w:t1:2")
        self.assertEqual(spec.purpose, "worker")
        self.assertEqual(spec.max_output_tokens, 777)
        self.assertTrue(spec.stream)
        self.assertEqual(spec.priority, "interactive")
        self.assertEqual(spec.meta, {"task_id": "t1", "attempt": 2})
        self.assertIn("ops", spec.json_schema["properties"])
        text = spec.messages[0]["content"]
        self.assertIn("make add", text)
        self.assertIn("bad thing", text)
        self.assertIn("prev out", text)
        self.assertIn("def add(a,b)", text)

    def test_build_first_no_feedback(self):
        spec = build_worker_call("r", _task(), 1, "w", 0.2, "bad", "prev", [])
        self.assertNotIn("bad", spec.messages[0]["content"])

    def test_parse(self):
        good = {"ops": [{"op": "write_file", "path": "a.py", "content": "x"}], "notes": "n"}
        r = CallResult(call_id="c", ok=True, parsed=good)
        self.assertEqual(parse_output(r).ops[0].path, "a.py")
        r = CallResult(call_id="c", ok=True, content="```json\n" + json.dumps(good) + "\n```")
        self.assertEqual(parse_output(r).notes, "n")
        self.assertIsNone(parse_output(CallResult(call_id="c", ok=True, content="nope")))
        self.assertIsNone(parse_output(CallResult(call_id="c", ok=False, parsed=good)))
        self.assertIsNone(parse_output(CallResult(call_id="c", ok=True, parsed={"ops": 5})))
        b = parse_output(CallResult(call_id="c", ok=True, parsed={"blocked": "why"}))
        self.assertEqual(b.blocked, "why")

    def test_feedback(self):
        self.assertEqual(feedback_text([]), "")
        tail = "\n".join(f"line{i}" for i in range(100))
        f = CheckResult(ok=False, check=Check(type="command", cmd="pytest"), exit_code=1, output_tail=tail)
        out = feedback_text([f], max_lines=60)
        lines = out.splitlines()
        self.assertEqual(len(lines), 60)
        self.assertEqual(lines[-1], "line99")
        short = feedback_text([f.model_copy(update={"output_tail": "boom"})])
        self.assertIn("pytest", short)
        self.assertIn("boom", short)


if __name__ == "__main__":
    unittest.main()
