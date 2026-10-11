"""Tests for council.gateway.ctx_guard. Run: python -m unittest tests.test_gateway_ctx_guard -v"""

from __future__ import annotations

import copy
import unittest

from council.gateway.ctx_guard import est_tokens, fit_messages, messages_tokens, overflow


def msgs(sys_len: int, mid_len: int, user_len: int) -> list[dict]:
    return [
        {"role": "system", "content": "S" * sys_len},
        {"role": "assistant", "content": "M" * mid_len},
        {"role": "user", "content": "U" * user_len},
    ]


class TestTokens(unittest.TestCase):
    def test_est_min_one(self) -> None:
        self.assertEqual(est_tokens(""), 1)

    def test_est_ratio(self) -> None:
        self.assertEqual(est_tokens("a" * 360), 100)

    def test_messages_tokens_overhead(self) -> None:
        m = [{"role": "user", "content": "a" * 360}, {"role": "user", "content": "b" * 36}]
        self.assertEqual(messages_tokens(m), 100 + 4 + 10 + 4)


class TestFit(unittest.TestCase):
    def test_fits_unchanged(self) -> None:
        m = msgs(100, 100, 100)
        out, info = fit_messages(m, 4096, 512)
        self.assertEqual(out, m)
        self.assertFalse(info["trimmed"])
        self.assertEqual(overflow(m, 4096, 512), 0)

    def test_trims_longest_middle(self) -> None:
        m = msgs(200, 20000, 200)
        out, info = fit_messages(m, 2048, 512)
        self.assertTrue(info["trimmed"])
        self.assertTrue(info["fits"])
        self.assertLessEqual(info["after"], 2048 - 512 - 256)
        self.assertLess(info["after"], info["before"])
        self.assertEqual([c["index"] for c in info["cuts"]], [1])
        self.assertIn("characters to fit the context window", out[1]["content"])
        self.assertTrue(out[1]["content"].startswith("M"))
        self.assertTrue(out[1]["content"].endswith("M"))
        self.assertEqual(out[0], m[0])
        self.assertEqual(out[2], m[2])

    def test_removed_chars_reported(self) -> None:
        m = msgs(200, 20000, 200)
        out, info = fit_messages(m, 2048, 512)
        n = info["cuts"][0]["removed_chars"]
        self.assertIn(f"[cut {n} characters", out[1]["content"])
        self.assertEqual(len(out[1]["content"]), 20000 - n + len(f"\n...[cut {n} characters to fit the context window]...\n"))

    def test_input_not_mutated(self) -> None:
        m = msgs(200, 20000, 200)
        snap = copy.deepcopy(m)
        out, _ = fit_messages(m, 2048, 512)
        self.assertEqual(m, snap)
        self.assertIsNot(out, m)

    def test_system_head_protected(self) -> None:
        m = msgs(30000, 100, 100)
        out, info = fit_messages(m, 2048, 512)
        self.assertTrue(info["trimmed"])
        self.assertTrue(out[0]["content"].startswith("S" * 1500))
        self.assertEqual(out[1], m[1])
        self.assertEqual(out[2], m[2])

    def test_last_user_tail_protected(self) -> None:
        m = msgs(100, 100, 30000)
        m[2]["content"] = "A" * 29000 + "Z" * 1000
        out, info = fit_messages(m, 2048, 512)
        self.assertTrue(info["trimmed"])
        self.assertTrue(out[2]["content"].endswith("Z" * 1000))
        tail = m[2]["content"][-1500:]
        self.assertTrue(out[2]["content"].endswith(tail))
        self.assertEqual(out[0], m[0])

    def test_only_last_user_is_protected(self) -> None:
        m = [
            {"role": "user", "content": "x" * 20000},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "q" * 100},
        ]
        out, info = fit_messages(m, 2048, 512)
        self.assertEqual([c["index"] for c in info["cuts"]], [0])
        self.assertEqual(out[2], m[2])

    def test_spreads_over_messages_when_one_exhausted(self) -> None:
        # protected regions leave little to cut in the system message; mid must also be cut
        m = msgs(3000, 6000, 3000)
        out, info = fit_messages(m, 1500, 300)
        self.assertTrue(info["trimmed"])
        self.assertGreaterEqual(len(info["cuts"]), 2)
        self.assertTrue(out[0]["content"].startswith("S" * 1500))
        self.assertTrue(out[2]["content"].endswith("U" * 1500))

    def test_impossible_budget_reports_not_fit(self) -> None:
        m = msgs(5000, 100, 5000)
        out, info = fit_messages(m, 600, 300)
        self.assertTrue(info["trimmed"])
        self.assertFalse(info["fits"])
        self.assertTrue(out[0]["content"].startswith("S" * 1500))
        self.assertTrue(out[2]["content"].endswith("U" * 1500))

    def test_deterministic(self) -> None:
        m = msgs(2000, 20000, 2000)
        self.assertEqual(fit_messages(m, 2048, 512), fit_messages(m, 2048, 512))

    def test_reserve_param(self) -> None:
        m = msgs(100, 4000, 100)
        _, a = fit_messages(m, 2048, 512, reserve=0)
        _, b = fit_messages(m, 2048, 512, reserve=1000)
        self.assertFalse(a["trimmed"])
        self.assertTrue(b["trimmed"])


class TestOverflow(unittest.TestCase):
    def test_overflow_positive(self) -> None:
        m = msgs(100, 20000, 100)
        o = overflow(m, 2048, 512)
        self.assertEqual(o, messages_tokens(m) - (2048 - 512 - 256))
        self.assertGreater(o, 0)


if __name__ == "__main__":
    unittest.main()
