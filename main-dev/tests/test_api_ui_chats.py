import json
import unittest

from council.api.ui_chats import DEFAULTS, UiChats
from council.core.store import Store


class Clock:
    def __init__(self):
        self.t = 1_760_000_000.0

    def __call__(self):
        self.t += 1.0
        return self.t


class UiChatsTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.chats = UiChats(self.store, now=Clock())

    def tearDown(self):
        self.store.close()

    def test_create_get_shape(self):
        c = self.chats.create()
        self.assertEqual(len(c["id"]), 32)
        self.assertEqual(
            set(c), {"id", "title", "pinned", "createdAt", "updatedAt", "messageCount", "messages"}
        )
        self.assertTrue(c["createdAt"].endswith("Z"))
        self.assertEqual(self.chats.get(c["id"]), c)
        self.assertIsNone(self.chats.get("nope"))

    def test_title_from_first_user_message(self):
        c = self.chats.create()
        self.chats.add_message(c["id"], "user", "x" * 100)
        self.assertEqual(self.chats.get(c["id"])["title"], "x" * 48)
        self.chats.add_message(c["id"], "user", "second")
        self.assertEqual(self.chats.get(c["id"])["title"], "x" * 48)
        named = self.chats.create("Mine")
        self.chats.add_message(named["id"], "user", "hello")
        self.assertEqual(self.chats.get(named["id"])["title"], "Mine")

    def test_message_shape_and_set(self):
        c = self.chats.create()
        m = self.chats.add_message(c["id"], "assistant", "", status="writing", run_id="r1")
        self.assertEqual(
            set(m),
            {"id", "chatId", "role", "text", "status", "createdAt", "model", "tokensPerSecond",
             "answerTokens", "error", "runId"},
        )
        self.assertEqual(m["runId"], "r1")
        out = self.chats.set_message(
            c["id"], m["id"], text="done", status="complete", tokensPerSecond=3.5, answerTokens=7,
            model="Council",
        )
        self.assertEqual(out["text"], "done")
        self.assertEqual(self.chats.get(c["id"])["messages"][0]["tokensPerSecond"], 3.5)
        self.assertIsNone(self.chats.set_message(c["id"], "nope", text="x"))
        self.assertIsNone(self.chats.set_message("nope", m["id"], text="x"))
        with self.assertRaises(ValueError):
            self.chats.set_message(c["id"], m["id"], role="user")
        with self.assertRaises(KeyError):
            self.chats.add_message("nope", "user", "x")

    def test_list_order_preview_query(self):
        a = self.chats.create("Alpha")
        b = self.chats.create("Beta")
        self.chats.add_message(a["id"], "user", "tell me about the purple zebra " + "y" * 200)
        rows = self.chats.list()
        self.assertEqual([r["id"] for r in rows], [a["id"], b["id"]])
        self.assertEqual(len(rows[0]["preview"]), 80)
        self.assertIsNone(rows[0]["match"])
        self.assertEqual(rows[0]["messageCount"], 1)
        self.assertEqual(rows[1]["preview"], "")
        hits = self.chats.list("ZEBRA")
        self.assertEqual([r["id"] for r in hits], [a["id"]])
        self.assertIn("zebra", hits[0]["match"])
        self.assertLessEqual(len(hits[0]["match"]), 120)
        self.assertEqual([r["id"] for r in self.chats.list("beta")], [b["id"]])
        self.assertEqual(self.chats.list("nothing here"), [])

    def test_update_delete(self):
        c = self.chats.create()
        u = self.chats.update(c["id"], title="New name", pinned=True)
        self.assertEqual((u["title"], u["pinned"]), ("New name", True))
        self.chats.add_message(c["id"], "user", "hi")
        self.assertEqual(self.chats.get(c["id"])["title"], "New name")
        self.assertIsNone(self.chats.update("nope", title="x"))
        self.assertTrue(self.chats.delete(c["id"]))
        self.assertFalse(self.chats.delete(c["id"]))
        self.assertEqual(self.chats.list(), [])

    def test_last_user_remove_assistant_history(self):
        c = self.chats.create()
        self.assertIsNone(self.chats.last_user_message(c["id"]))
        self.assertEqual(self.chats.history_block(c["id"]), "")
        self.chats.add_message(c["id"], "user", "q1")
        self.chats.add_message(c["id"], "assistant", "a" * 700)
        self.chats.add_message(c["id"], "user", "q2")
        self.chats.remove_last_assistant(c["id"])  # last is a user message: nothing happens
        self.assertEqual(self.chats.get(c["id"])["messageCount"], 3)
        self.chats.add_message(c["id"], "assistant", "a2")
        self.assertEqual(self.chats.last_user_message(c["id"])["text"], "q2")
        block = self.chats.history_block(c["id"])
        self.assertTrue(block.startswith("Conversation so far:"))
        self.assertIn("User: q1", block)
        self.assertIn("Council: " + "a" * 600 + "...", block)
        self.assertNotIn("a" * 601, block)
        self.assertEqual(len(self.chats.history_block(c["id"], max_messages=2).splitlines()), 3)
        self.chats.remove_last_assistant(c["id"])
        msgs = self.chats.get(c["id"])["messages"]
        self.assertEqual([m["text"] for m in msgs][-1], "q2")
        self.chats.remove_last_assistant("nope")

    def test_export(self):
        c = self.chats.create("My chat")
        self.chats.add_message(c["id"], "user", "hello")
        self.chats.add_message(c["id"], "assistant", "hi there")
        md = self.chats.export(c["id"], "markdown")
        self.assertEqual(md["mime"], "text/markdown")
        self.assertTrue(md["filename"].endswith(".md"))
        self.assertEqual(md["text"], "# My chat\n\n**You:** hello\n\n**Council:** hi there\n")
        js = self.chats.export(c["id"], "json")
        self.assertEqual(json.loads(js["text"])["messages"][1]["text"], "hi there")
        self.assertIsNone(self.chats.export("nope", "json"))
        with self.assertRaises(ValueError):
            self.chats.export(c["id"], "pdf")

    def test_settings(self):
        s = self.chats.settings()
        self.assertEqual(s["modelAddress"], DEFAULTS["modelAddress"])
        self.assertEqual(s["maxAnswerTokens"], 1024)
        self.assertFalse(s["hasModelKey"])
        s = self.chats.update_settings(modelKey="secret", maxAnswerTokens=256, systemPrompt="be kind")
        self.assertEqual(set(s), {"modelAddress", "hasModelKey", "systemPrompt", "maxAnswerTokens"})
        self.assertTrue(s["hasModelKey"])
        self.assertEqual((s["maxAnswerTokens"], s["systemPrompt"]), (256, "be kind"))
        self.assertFalse(self.chats.update_settings(modelKey="")["hasModelKey"])

    def test_survives_new_instance(self):
        c = self.chats.create("Keep")
        again = UiChats(self.store)
        self.assertEqual(again.get(c["id"])["title"], "Keep")


if __name__ == "__main__":
    unittest.main()
