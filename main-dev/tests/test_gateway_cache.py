"""Tests for council.gateway.cache (spec 7.5). Run: python -m unittest tests.test_gateway_cache -v"""

from __future__ import annotations

import unittest

from council.core.schemas import CallResult, CallSpec
from council.gateway.cache import CallCache, cache_key


class DictStore:
    def __init__(self) -> None:
        self.data: dict[str, CallResult] = {}
        self.gets = 0
        self.puts = 0

    def cache_get(self, key: str):
        self.gets += 1
        return self.data.get(key)

    def cache_put(self, key: str, result: CallResult) -> None:
        self.puts += 1
        self.data[key] = result


def make_spec(**overrides) -> CallSpec:
    base = dict(
        model_id="model-a",
        messages=[{"role": "user", "content": "hi"}],
        cacheable=True,
        seed=7,
        temperature=0.2,
    )
    base.update(overrides)
    return CallSpec(**base)


def make_result(call_id: str = "c1", ok: bool = True) -> CallResult:
    return CallResult(call_id=call_id, ok=ok, content="answer", model_id="model-a")


class CacheKeyTests(unittest.TestCase):
    def test_same_spec_same_key(self):
        self.assertEqual(cache_key(make_spec()), cache_key(make_spec()))

    def test_call_id_and_meta_do_not_affect_key(self):
        a = make_spec(call_id="x", meta={"seat_no": 1})
        b = make_spec(call_id="y", meta={"seat_no": 2}, run_id="r")
        self.assertEqual(cache_key(a), cache_key(b))

    def test_key_is_sha256_hex(self):
        key = cache_key(make_spec())
        self.assertEqual(len(key), 64)
        int(key, 16)

    def test_each_output_field_changes_key(self):
        base = cache_key(make_spec())
        variants = [
            make_spec(model_id="model-b"),
            make_spec(messages=[{"role": "user", "content": "bye"}]),
            make_spec(json_schema={"type": "object"}),
            make_spec(reasoning="max"),
            make_spec(temperature=0.9),
            make_spec(top_p=0.5),
            make_spec(seed=8),
            make_spec(max_output_tokens=99),
            make_spec(max_reasoning_tokens=500),
        ]
        keys = [cache_key(v) for v in variants]
        for k in keys:
            self.assertNotEqual(k, base)
        self.assertEqual(len(set(keys)), len(keys))

    def test_quant_changes_key(self):
        self.assertNotEqual(cache_key(make_spec(), "q4"), cache_key(make_spec(), "q8"))
        self.assertEqual(cache_key(make_spec()), cache_key(make_spec(), ""))

    def test_dict_key_order_does_not_matter(self):
        a = make_spec(json_schema={"a": 1, "b": {"x": 1, "y": 2}})
        b = make_spec(json_schema={"b": {"y": 2, "x": 1}, "a": 1})
        self.assertEqual(cache_key(a), cache_key(b))

    def test_unicode_is_stable(self):
        spec = make_spec(messages=[{"role": "user", "content": "héllo"}])
        self.assertEqual(cache_key(spec), cache_key(spec))


class CallCacheTests(unittest.TestCase):
    def setUp(self):
        self.store = DictStore()
        self.cache = CallCache(self.store)

    def test_put_then_get_hits(self):
        spec = make_spec()
        self.assertTrue(self.cache.put(spec, "", make_result()))
        got = self.cache.get(spec, "")
        self.assertIsNotNone(got)
        self.assertEqual(got.content, "answer")
        self.assertTrue(got.cached)
        self.assertEqual((self.cache.hits, self.cache.misses), (1, 0))

    def test_miss_counts(self):
        self.assertIsNone(self.cache.get(make_spec(), ""))
        self.assertEqual((self.cache.hits, self.cache.misses), (0, 1))

    def test_not_cacheable_get_returns_none_without_lookup(self):
        spec = make_spec(cacheable=False)
        self.store.data[cache_key(spec)] = make_result()
        self.assertIsNone(self.cache.get(spec, ""))
        self.assertEqual(self.store.gets, 0)
        self.assertEqual(self.cache.misses, 1)

    def test_no_seed_get_returns_none_without_lookup(self):
        spec = make_spec(seed=None)
        self.store.data[cache_key(spec)] = make_result()
        self.assertIsNone(self.cache.get(spec, ""))
        self.assertEqual(self.store.gets, 0)

    def test_not_cacheable_put_is_skipped(self):
        spec = make_spec(cacheable=False)
        self.assertFalse(self.cache.put(spec, "", make_result()))
        self.assertEqual(self.store.puts, 0)

    def test_no_seed_put_is_skipped(self):
        spec = make_spec(seed=None)
        self.assertFalse(self.cache.put(spec, "", make_result()))
        self.assertEqual(self.store.puts, 0)

    def test_failed_result_is_not_stored(self):
        spec = make_spec()
        self.assertFalse(self.cache.put(spec, "", make_result(ok=False)))
        self.assertEqual(self.store.puts, 0)
        self.assertIsNone(self.cache.get(spec, ""))

    def test_quant_separates_entries(self):
        spec = make_spec()
        self.cache.put(spec, "q4", make_result())
        self.assertIsNone(self.cache.get(spec, "q8"))
        self.assertIsNotNone(self.cache.get(spec, "q4"))

    def test_different_seed_misses(self):
        self.cache.put(make_spec(seed=1), "", make_result())
        self.assertIsNone(self.cache.get(make_spec(seed=2), ""))

    def test_stored_result_is_not_mutated_by_hit(self):
        spec = make_spec()
        original = make_result()
        self.cache.put(spec, "", original)
        self.cache.get(spec, "")
        self.assertFalse(original.cached)
        self.assertFalse(self.store.data[cache_key(spec)].cached)


if __name__ == "__main__":
    unittest.main()
