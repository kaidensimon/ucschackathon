import unittest

from council.probe import layout
from council.probe.layout import (
    LAYOUT_VERSION, probe_messages, probe_text, statement_text)


class ProbeLayoutTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(LAYOUT_VERSION, 1)

    def test_exact_text(self):
        self.assertEqual(
            probe_text("What is 2+2?", "It is 4."),
            "Question: What is 2+2?\nStatement: It is 4.\nThe statement above is")

    def test_task_whitespace_squeezed(self):
        t = probe_text("  a \n\n b\t\tc  ", "x")
        self.assertTrue(t.startswith("Question: a b c\nStatement: x\n"))

    def test_task_clipped_600(self):
        t = probe_text("a" * 1000, "s")
        line = t.split("\n")[0]
        self.assertEqual(line, "Question: " + "a" * 600)

    def test_task_clip_after_squeeze(self):
        # 700 spaces then text: squeeze first, so the text survives the clip
        t = probe_text(" " * 700 + "hello", "s")
        self.assertEqual(t.split("\n")[0], "Question: hello")

    def test_statement_clipped_400(self):
        t = probe_text("q", "b" * 900)
        self.assertEqual(t.split("\n")[1], "Statement: " + "b" * 400)

    def test_ends_with_tail(self):
        self.assertTrue(probe_text("q", "s").endswith("The statement above is"))
        self.assertTrue(statement_text("s").endswith("The statement above is"))

    def test_messages(self):
        m = probe_messages("q", "s")
        self.assertEqual(m, [{"role": "user", "content": probe_text("q", "s")}])

    def test_statement_text(self):
        self.assertEqual(statement_text("It is 4."),
                         "Statement: It is 4.\nThe statement above is")
        self.assertEqual(statement_text("c" * 500), "Statement: " + "c" * 400
                         + "\nThe statement above is")

    def test_empty_and_none(self):
        self.assertEqual(probe_text("", ""),
                         "Question: \nStatement: \nThe statement above is")
        self.assertEqual(probe_text(None, None), probe_text("", ""))
        self.assertEqual(statement_text(None), "Statement: \nThe statement above is")

    def test_deterministic(self):
        self.assertEqual(probe_text("q", "s"), probe_text("q", "s"))

    def test_train_and_live_same(self):
        # one function, one text, whatever the caller
        self.assertEqual(probe_messages("q", "s")[0]["content"], probe_text("q", "s"))

    def test_public_names(self):
        self.assertEqual(set(layout.__all__),
                         {"LAYOUT_VERSION", "probe_text", "probe_messages", "statement_text"})


if __name__ == "__main__":
    unittest.main()
