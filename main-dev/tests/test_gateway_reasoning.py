"""Tests for council/gateway/reasoning.py (spec 7.4). Run: python -m unittest tests.test_gateway_reasoning -v"""

import unittest

from council.core.schemas import ModelEntry, ReasoningControl
from council.gateway.reasoning import apply_caps, request_fields, strip_reasoning


def _entry(**levels) -> ModelEntry:
    return ModelEntry(
        id="m1",
        reasoning=ReasoningControl(kind="toggle", **levels),
    )


class StripReasoningTests(unittest.TestCase):
    def test_plain_text_passes_through(self):
        self.assertEqual(strip_reasoning("  Paris.  "), ("Paris.", ""))

    def test_empty(self):
        self.assertEqual(strip_reasoning(""), ("", ""))

    def test_think_block(self):
        content, reasoning = strip_reasoning("<think>2 + 2 is 4</think>The answer is 4.")
        self.assertEqual(content, "The answer is 4.")
        self.assertEqual(reasoning, "2 + 2 is 4")

    def test_thinking_block(self):
        content, reasoning = strip_reasoning("<thinking>step one</thinking>\n\nDone.")
        self.assertEqual(content, "Done.")
        self.assertEqual(reasoning, "step one")

    def test_multiple_blocks_joined(self):
        content, reasoning = strip_reasoning(
            "<think>a</think>x<thinking>b</thinking>y"
        )
        self.assertEqual(content, "xy")
        self.assertEqual(reasoning, "a\n\nb")

    def test_unclosed_opening_tag_rest_is_reasoning(self):
        content, reasoning = strip_reasoning("Intro <think>still going, no answer")
        self.assertEqual(content, "Intro")
        self.assertEqual(reasoning, "still going, no answer")

    def test_closing_tag_without_opening_before_is_reasoning(self):
        content, reasoning = strip_reasoning("secret thoughts</think>Final answer.")
        self.assertEqual(content, "Final answer.")
        self.assertEqual(reasoning, "secret thoughts")

    def test_stray_close_after_block(self):
        content, reasoning = strip_reasoning("<think>a</think>pre</think>post")
        self.assertEqual(content, "post")
        self.assertEqual(reasoning, "a\n\npre")

    def test_case_insensitive_tags(self):
        content, reasoning = strip_reasoning("<THINK>x</Think>ok")
        self.assertEqual(content, "ok")
        self.assertEqual(reasoning, "x")

    def test_channel_style(self):
        text = (
            "<|channel|>analysis<|message|>weigh the options<|end|>"
            "<|start|>assistant<|channel|>final<|message|>Use option B.<|return|>"
        )
        content, reasoning = strip_reasoning(text)
        self.assertEqual(content, "Use option B.")
        self.assertEqual(reasoning, "weigh the options")

    def test_channel_style_without_final_gives_empty_content(self):
        text = "<|channel|>analysis<|message|>only thinking<|end|>"
        content, reasoning = strip_reasoning(text)
        self.assertEqual(content, "")
        self.assertEqual(reasoning, "only thinking")

    def test_no_markers_keeps_angle_text(self):
        content, reasoning = strip_reasoning("use a < b and c > d")
        self.assertEqual(content, "use a < b and c > d")
        self.assertEqual(reasoning, "")


class RequestFieldsTests(unittest.TestCase):
    def test_returns_level_fields(self):
        entry = _entry(
            off={"chat_template_kwargs": {"enable_thinking": False}},
            council={"chat_template_kwargs": {"enable_thinking": True}},
            max={"reasoning_effort": "high"},
        )
        self.assertEqual(
            request_fields(entry, "council"),
            {"chat_template_kwargs": {"enable_thinking": True}},
        )
        self.assertEqual(request_fields(entry, "max"), {"reasoning_effort": "high"})

    def test_missing_level_is_empty(self):
        entry = _entry(council={"x": 1})
        self.assertEqual(request_fields(entry, "off"), {})
        self.assertEqual(request_fields(entry, "max"), {})

    def test_returns_copy(self):
        entry = _entry(council={"x": 1})
        request_fields(entry, "council")["x"] = 99
        self.assertEqual(request_fields(entry, "council"), {"x": 1})

    def test_unknown_level_raises(self):
        with self.assertRaises(ValueError):
            request_fields(_entry(), "turbo")


class ApplyCapsTests(unittest.TestCase):
    def test_server_enforces(self):
        self.assertEqual(
            apply_caps(1024, 512, True),
            {"max_tokens": 1024, "reasoning_budget": 512},
        )

    def test_server_does_not_enforce_single_cap(self):
        self.assertEqual(apply_caps(1024, 512, False), {"max_tokens": 1024})

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            apply_caps(-1, 0, True)
        with self.assertRaises(ValueError):
            apply_caps(10, -5, False)


if __name__ == "__main__":
    unittest.main()
