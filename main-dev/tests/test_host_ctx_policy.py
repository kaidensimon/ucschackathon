"""Tests for council.host.ctx_policy (pure functions)."""

from __future__ import annotations

import unittest

from council.host.ctx_policy import (
    CTX_BUCKETS,
    ctx_for,
    est_tokens,
    needed_ctx,
)


class CtxForTests(unittest.TestCase):
    def test_base_roles(self) -> None:
        self.assertEqual(ctx_for("chair"), 16384)
        self.assertEqual(ctx_for("planner"), 16384)
        self.assertEqual(ctx_for("worker"), 8192)
        self.assertEqual(ctx_for("senior_worker"), 12288)
        self.assertEqual(ctx_for("clerk"), 8192)
        self.assertEqual(ctx_for("review"), 16384)
        self.assertEqual(ctx_for("probe"), 2048)

    def test_seat_by_mode(self) -> None:
        self.assertEqual(ctx_for("seat"), 16384)
        self.assertEqual(ctx_for("seat", "standard"), 16384)
        self.assertEqual(ctx_for("seat", "deep"), 24576)
        self.assertEqual(ctx_for("seat", "quick"), 8192)

    def test_unknown_mode_is_standard_for_seat(self) -> None:
        self.assertEqual(ctx_for("seat", "turbo"), 16384)

    def test_mode_ignored_for_other_roles(self) -> None:
        self.assertEqual(ctx_for("worker", "deep"), 8192)
        self.assertEqual(ctx_for("chair", "quick"), 16384)

    def test_unknown_role_default(self) -> None:
        self.assertEqual(ctx_for("nobody"), 8192)
        self.assertEqual(ctx_for(""), 8192)

    def test_overrides_win(self) -> None:
        self.assertEqual(ctx_for("worker", overrides={"worker": 4096}), 4096)
        self.assertEqual(ctx_for("seat", "deep", overrides={"seat": 2048}), 2048)

    def test_override_for_unknown_role(self) -> None:
        self.assertEqual(ctx_for("custom", overrides={"custom": 32768}), 32768)

    def test_override_other_role_ignored(self) -> None:
        self.assertEqual(ctx_for("chair", overrides={"worker": 4096}), 16384)

    def test_empty_overrides(self) -> None:
        self.assertEqual(ctx_for("probe", overrides={}), 2048)

    def test_override_none_is_no_override(self) -> None:
        self.assertEqual(ctx_for("probe", overrides=None), 2048)


class NeededCtxTests(unittest.TestCase):
    def test_small_request_gets_smallest_bucket(self) -> None:
        self.assertEqual(needed_ctx(100, 100), 2048)

    def test_zero_request(self) -> None:
        self.assertEqual(needed_ctx(0, 0), 2048)

    def test_exact_fit_without_margin(self) -> None:
        self.assertEqual(needed_ctx(1000, 1048, margin=1.0), 2048)

    def test_just_over_bucket_moves_up(self) -> None:
        self.assertEqual(needed_ctx(1000, 1049, margin=1.0), 4096)

    def test_margin_applied(self) -> None:
        # 1800 * 1.15 = 2070 > 2048 -> next bucket.
        self.assertEqual(needed_ctx(1800, 0), 4096)
        # 1700 * 1.15 = 1955 <= 2048.
        self.assertEqual(needed_ctx(1700, 0), 2048)

    def test_reasoning_counts(self) -> None:
        self.assertEqual(needed_ctx(1000, 0, reasoning=0), 2048)
        self.assertEqual(needed_ctx(1000, 0, reasoning=2000), 4096)

    def test_output_counts(self) -> None:
        self.assertEqual(needed_ctx(100, 3000), 4096)

    def test_walks_every_bucket(self) -> None:
        for bucket in CTX_BUCKETS:
            # Request sized to exactly fill this bucket with margin 1.0.
            self.assertEqual(needed_ctx(bucket, 0, margin=1.0), bucket)
            self.assertEqual(needed_ctx(bucket - 1, 0, margin=1.0), bucket)

    def test_overflow_returns_largest(self) -> None:
        self.assertEqual(needed_ctx(40000, 0), 32768)
        self.assertEqual(needed_ctx(32768, 0, margin=1.0), 32768)
        self.assertEqual(needed_ctx(32769, 0, margin=1.0), 32768)

    def test_result_is_always_a_bucket(self) -> None:
        for p in (0, 1, 500, 3000, 9000, 20000, 30000, 100000):
            self.assertIn(needed_ctx(p, 0), CTX_BUCKETS)

    def test_negative_inputs_clamped(self) -> None:
        self.assertEqual(needed_ctx(-500, -500, reasoning=-1), 2048)

    def test_monotonic_in_prompt(self) -> None:
        prev = 0
        for p in range(0, 40000, 500):
            cur = needed_ctx(p, 256)
            self.assertGreaterEqual(cur, prev)
            prev = cur


class EstTokensTests(unittest.TestCase):
    def test_empty_is_one(self) -> None:
        self.assertEqual(est_tokens(""), 1)

    def test_short_text_never_below_one(self) -> None:
        self.assertEqual(est_tokens("a"), 1)
        self.assertEqual(est_tokens("ab"), 1)

    def test_rounding(self) -> None:
        # 36 chars / 3.6 = 10
        self.assertEqual(est_tokens("x" * 36), 10)
        # 18 chars / 3.6 = 5
        self.assertEqual(est_tokens("x" * 18), 5)
        # 7 chars / 3.6 = 1.94 -> 2
        self.assertEqual(est_tokens("x" * 7), 2)

    def test_scales_with_length(self) -> None:
        self.assertGreater(est_tokens("x" * 1000), est_tokens("x" * 100))

    def test_uses_character_count_not_bytes(self) -> None:
        # 4 multi-byte chars -> 4 chars -> round(4/3.6)=1
        self.assertEqual(est_tokens("éééé"), 1)
        # 36 emoji-free non-ascii chars -> 10
        self.assertEqual(est_tokens("é" * 36), 10)


if __name__ == "__main__":
    unittest.main()
