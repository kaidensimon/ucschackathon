"""Tests for council/host/model_checks.py. Standard library unittest only."""

import json
import tempfile
import unittest
from pathlib import Path

from council.core.schemas import ModelEntry
from council.core.schemas_v15 import MeasuredModel
from council.host.model_checks import by_model_id, default_path, load_checks


def _row(**over):
    row = {
        "ok": True,
        "error": None,
        "size_gib": 9.5,
        "ram_gib": 11.02,
        "tps": 41.25,
        "json_ok": True,
        "think_ok": False,
        "checked_at": "2026-10-11T10:00:00",
    }
    row.update(over)
    return row


class _TmpMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, content, name="model_checks.json"):
        path = self.dir / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        elif isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_text(json.dumps(content), encoding="utf-8")
        return path


class DefaultPathTests(unittest.TestCase):
    def test_joins_file_name(self):
        home = Path("some") / "box"
        self.assertEqual(default_path(home), home / "model_checks.json")

    def test_returns_path_type(self):
        self.assertIsInstance(default_path(Path("x")), Path)


class LoadChecksMissingOrBadTests(_TmpMixin, unittest.TestCase):
    def test_missing_file_gives_empty(self):
        self.assertEqual(load_checks(self.dir / "nope.json"), {})

    def test_directory_instead_of_file_gives_empty(self):
        self.assertEqual(load_checks(self.dir), {})

    def test_empty_file_gives_empty(self):
        self.assertEqual(load_checks(self.write("")), {})

    def test_bad_json_gives_empty(self):
        self.assertEqual(load_checks(self.write("{not json")), {})

    def test_non_utf8_bytes_give_empty(self):
        self.assertEqual(load_checks(self.write(b"\xff\xfe\x00bad")), {})

    def test_top_level_list_gives_empty(self):
        self.assertEqual(load_checks(self.write([_row()])), {})

    def test_top_level_scalar_gives_empty(self):
        self.assertEqual(load_checks(self.write("42")), {})

    def test_accepts_str_path(self):
        self.assertEqual(load_checks(str(self.dir / "nope.json")), {})


class LoadChecksMappingTests(_TmpMixin, unittest.TestCase):
    def test_full_row_maps_every_field(self):
        path = self.write({"gpt-oss:20b": _row()})
        out = load_checks(path)
        self.assertEqual(list(out), ["gpt-oss:20b"])
        m = out["gpt-oss:20b"]
        self.assertIsInstance(m, MeasuredModel)
        self.assertEqual(m.tag, "gpt-oss:20b")
        self.assertEqual(m.model_id, "gpt-oss:20b")
        self.assertTrue(m.ok)
        self.assertEqual(m.reported_gib, 9.5)
        self.assertEqual(m.ram_gib, 11.02)
        self.assertEqual(m.tps, 41.25)
        self.assertIs(m.json_ok, True)
        self.assertIs(m.think_ok, False)
        self.assertEqual(m.error, "")

    def test_error_text_is_kept_and_ok_false(self):
        path = self.write({"bad:1b": _row(ok=False, error="HTTP 500: out of memory",
                                          size_gib=None, ram_gib=None, tps=None,
                                          json_ok=None, think_ok=None)})
        m = load_checks(path)["bad:1b"]
        self.assertFalse(m.ok)
        self.assertEqual(m.error, "HTTP 500: out of memory")
        self.assertIsNone(m.reported_gib)
        self.assertIsNone(m.ram_gib)
        self.assertIsNone(m.tps)
        self.assertIsNone(m.json_ok)
        self.assertIsNone(m.think_ok)

    def test_null_error_becomes_empty_string(self):
        m = load_checks(self.write({"a:1": _row(error=None)}))["a:1"]
        self.assertEqual(m.error, "")

    def test_non_string_error_is_stringified(self):
        m = load_checks(self.write({"a:1": _row(error=500)}))["a:1"]
        self.assertEqual(m.error, "500")

    def test_checked_at_is_not_carried(self):
        m = load_checks(self.write({"a:1": _row()}))["a:1"]
        self.assertNotIn("checked_at", m.model_dump())

    def test_ok_only_true_for_json_true(self):
        path = self.write({"s:1": _row(ok="true"), "n:1": _row(ok=1), "m:1": _row(ok=None)})
        out = load_checks(path)
        self.assertFalse(out["s:1"].ok)
        self.assertFalse(out["n:1"].ok)
        self.assertFalse(out["m:1"].ok)

    def test_missing_fields_use_defaults(self):
        m = load_checks(self.write({"bare:1": {}}))["bare:1"]
        self.assertFalse(m.ok)
        self.assertIsNone(m.reported_gib)
        self.assertIsNone(m.ram_gib)
        self.assertIsNone(m.tps)
        self.assertIsNone(m.json_ok)
        self.assertIsNone(m.think_ok)
        self.assertEqual(m.error, "")

    def test_integer_numbers_become_float(self):
        m = load_checks(self.write({"i:1": _row(size_gib=9, ram_gib=10, tps=40)}))["i:1"]
        self.assertEqual(m.reported_gib, 9.0)
        self.assertIsInstance(m.reported_gib, float)
        self.assertEqual(m.ram_gib, 10.0)
        self.assertEqual(m.tps, 40.0)

    def test_bool_is_not_a_number(self):
        m = load_checks(self.write({"b:1": _row(size_gib=True, tps=False)}))["b:1"]
        self.assertIsNone(m.reported_gib)
        self.assertIsNone(m.tps)

    def test_string_numbers_are_not_numbers(self):
        m = load_checks(self.write({"s:1": _row(tps="41.2")}))["s:1"]
        self.assertIsNone(m.tps)

    def test_non_finite_numbers_are_dropped(self):
        # json.loads accepts NaN and Infinity; they must not reach the model.
        m = load_checks(self.write('{"nan:1": {"ok": true, "tps": NaN, "size_gib": Infinity}}'))["nan:1"]
        self.assertIsNone(m.tps)
        self.assertIsNone(m.reported_gib)

    def test_non_bool_flags_become_none(self):
        m = load_checks(self.write({"f:1": _row(json_ok=1, think_ok="yes")}))["f:1"]
        self.assertIsNone(m.json_ok)
        self.assertIsNone(m.think_ok)

    def test_non_dict_rows_are_skipped(self):
        path = self.write({"good:1": _row(), "list:1": [1, 2], "num:1": 3, "null:1": None,
                           "str:1": "ok"})
        out = load_checks(path)
        self.assertEqual(list(out), ["good:1"])

    def test_empty_tag_is_skipped(self):
        out = load_checks(self.write({"": _row(), "x:1": _row()}))
        self.assertEqual(list(out), ["x:1"])

    def test_many_rows_keep_their_keys(self):
        data = {f"m{i}:7b": _row(tps=float(i)) for i in range(20)}
        out = load_checks(self.write(data))
        self.assertEqual(set(out), set(data))
        self.assertEqual(out["m7:7b"].tps, 7.0)


class ByModelIdTests(unittest.TestCase):
    def setUp(self):
        self.checks = {
            "gpt-oss:20b": MeasuredModel(model_id="gpt-oss:20b", tag="gpt-oss:20b",
                                         ok=True, tps=40.0),
            "qwen3:32b": MeasuredModel(model_id="qwen3:32b", tag="qwen3:32b",
                                       ok=False, error="boom"),
        }
        self.registry = [
            ModelEntry(id="gpt-oss-20b", ollama_tag="gpt-oss:20b"),
            ModelEntry(id="qwen3-32b", ollama_tag="qwen3:32b"),
        ]

    def test_rekeys_by_registry_id(self):
        out = by_model_id(self.checks, self.registry)
        self.assertEqual(set(out), {"gpt-oss-20b", "qwen3-32b"})

    def test_model_id_becomes_registry_id(self):
        out = by_model_id(self.checks, self.registry)
        self.assertEqual(out["gpt-oss-20b"].model_id, "gpt-oss-20b")
        self.assertEqual(out["gpt-oss-20b"].tag, "gpt-oss:20b")
        self.assertEqual(out["gpt-oss-20b"].tps, 40.0)
        self.assertFalse(out["qwen3-32b"].ok)
        self.assertEqual(out["qwen3-32b"].error, "boom")

    def test_input_is_not_changed(self):
        by_model_id(self.checks, self.registry)
        self.assertEqual(self.checks["gpt-oss:20b"].model_id, "gpt-oss:20b")
        self.assertEqual(set(self.checks), {"gpt-oss:20b", "qwen3:32b"})

    def test_entry_without_tag_is_left_out(self):
        reg = self.registry + [ModelEntry(id="no-tag")]
        out = by_model_id(self.checks, reg)
        self.assertNotIn("no-tag", out)
        self.assertEqual(len(out), 2)

    def test_tag_without_check_row_is_left_out(self):
        reg = [ModelEntry(id="missing", ollama_tag="nothere:1b")]
        self.assertEqual(by_model_id(self.checks, reg), {})

    def test_empty_inputs(self):
        self.assertEqual(by_model_id({}, self.registry), {})
        self.assertEqual(by_model_id(self.checks, []), {})
        self.assertEqual(by_model_id({}, []), {})

    def test_match_is_exact(self):
        reg = [ModelEntry(id="x", ollama_tag="gpt-oss")]
        self.assertEqual(by_model_id(self.checks, reg), {})

    def test_two_entries_on_one_tag_both_map(self):
        reg = [ModelEntry(id="a", ollama_tag="gpt-oss:20b"),
               ModelEntry(id="b", ollama_tag="gpt-oss:20b")]
        out = by_model_id(self.checks, reg)
        self.assertEqual(out["a"].model_id, "a")
        self.assertEqual(out["b"].model_id, "b")


class RoundTripTests(_TmpMixin, unittest.TestCase):
    def test_file_to_registry_ids(self):
        path = self.write({
            "gpt-oss:20b": _row(size_gib=12.3, ram_gib=14.27, tps=55.5),
            "llama3:8b": _row(ok=False, error="HTTP 404: model not found",
                              size_gib=None, ram_gib=None, tps=None,
                              json_ok=None, think_ok=None),
        })
        reg = [
            ModelEntry(id="gpt-oss-20b", ollama_tag="gpt-oss:20b"),
            ModelEntry(id="llama-8b", ollama_tag="llama3:8b"),
            ModelEntry(id="unchecked", ollama_tag="other:1b"),
        ]
        out = by_model_id(load_checks(path), reg)
        self.assertEqual(set(out), {"gpt-oss-20b", "llama-8b"})
        self.assertEqual(out["gpt-oss-20b"].reported_gib, 12.3)
        self.assertEqual(out["gpt-oss-20b"].ram_gib, 14.27)
        self.assertFalse(out["llama-8b"].ok)
        self.assertEqual(out["llama-8b"].error, "HTTP 404: model not found")


if __name__ == "__main__":
    unittest.main()
