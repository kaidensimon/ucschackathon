"""Tests for council.core.util. Run from repo root: python -m unittest tests.test_core_util -v"""

import re
import unittest

from pydantic import BaseModel

from council.core.util import (
    FakeClock,
    SystemClock,
    chunk_words,
    est_tokens,
    iso,
    new_id,
    stable_hash,
)


class _Sample(BaseModel):
    b: int = 2
    a: str = "x"


class NewIdTests(unittest.TestCase):
    def test_shape(self):
        value = new_id("run")
        self.assertRegex(value, r"^run_[0-9a-f]{12}$")

    def test_unique(self):
        self.assertNotEqual(new_id("x"), new_id("x"))


class ClockTests(unittest.TestCase):
    def test_system_clock_returns_float(self):
        now = SystemClock().now()
        self.assertIsInstance(now, float)
        self.assertGreater(now, 0.0)

    def test_fake_clock_default_and_advance(self):
        clock = FakeClock()
        self.assertEqual(clock.now(), 0.0)
        clock.advance(1.5)
        clock.advance(2)
        self.assertEqual(clock.now(), 3.5)

    def test_fake_clock_start(self):
        self.assertEqual(FakeClock(start=100.0).now(), 100.0)


class IsoTests(unittest.TestCase):
    def test_epoch_zero(self):
        self.assertEqual(iso(0.0), "1970-01-01T00:00:00+00:00")

    def test_known_value(self):
        self.assertEqual(iso(1_000_000_000.0), "2001-09-09T01:46:40+00:00")


class StableHashTests(unittest.TestCase):
    def test_key_order_does_not_matter(self):
        self.assertEqual(stable_hash({"a": 1, "b": 2}), stable_hash({"b": 2, "a": 1}))

    def test_is_sha256_hex(self):
        self.assertRegex(stable_hash({"a": 1}), r"^[0-9a-f]{64}$")

    def test_different_content_differs(self):
        self.assertNotEqual(stable_hash({"a": 1}), stable_hash({"a": 2}))

    def test_model_matches_its_dict(self):
        self.assertEqual(stable_hash(_Sample()), stable_hash({"a": "x", "b": 2}))

    def test_nested_model_in_list(self):
        self.assertEqual(stable_hash([_Sample()]), stable_hash([{"a": "x", "b": 2}]))

    def test_no_whitespace_in_canonical_form(self):
        import hashlib
        import json

        expected = hashlib.sha256(json.dumps({"a": [1, 2]}, sort_keys=True,
                                             separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(stable_hash({"a": [1, 2]}), expected)


class ChunkWordsTests(unittest.TestCase):
    def test_even_split(self):
        self.assertEqual(chunk_words("a b c d", 2), ["a b", "c d"])

    def test_uneven_split(self):
        self.assertEqual(chunk_words("a b c d e", 2), ["a b", "c d", "e"])

    def test_collapses_whitespace(self):
        self.assertEqual(chunk_words("  a \n b\tc  ", 2), ["a b", "c"])

    def test_empty_text(self):
        self.assertEqual(chunk_words("", 3), [])

    def test_n_larger_than_text(self):
        self.assertEqual(chunk_words("one two", 10), ["one two"])

    def test_n_below_one_raises(self):
        with self.assertRaises(ValueError):
            chunk_words("a b", 0)


class EstTokensTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(est_tokens(""), 0)

    def test_rounds_up(self):
        self.assertEqual(est_tokens("a"), 1)
        self.assertEqual(est_tokens("abcd"), 1)
        self.assertEqual(est_tokens("abcde"), 2)

    def test_eight_chars(self):
        self.assertEqual(est_tokens("12345678"), 2)


if __name__ == "__main__":
    unittest.main()
