import asyncio
import tempfile
import unittest

from council.chronicle.recall import keyword_embedding
from council.chronicle.service import Chronicle
from council.core.schemas import ChronicleEntry
from council.core.workspace import project_id


class FakeStore:
    def __init__(self, entries):
        self.entries = {e.id: e for e in entries}

    def chronicle_list(self):
        return list(self.entries.values())

    def chronicle_put(self, entry):
        self.entries[entry.id] = entry

    def chronicle_delete(self, id):
        self.entries.pop(id, None)


async def fake_embed(texts):
    return [keyword_embedding(t) for t in texts]


def mk(id, statement, **kw):
    return ChronicleEntry(id=id, statement=statement, embedding=keyword_embedding(statement), **kw)


class ChronicleServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pid = project_id(self.tmp.name)
        self.store = FakeStore([
            mk("a", "always use tabs in python files", kind="preference", scope="global",
               status="active", confidence=0.9),
            mk("b", "tests live in tests folder", kind="project_fact", scope=f"project:{self.pid}",
               status="provisional", confidence=0.5),
            mk("c", "other project fact", kind="project_fact", scope="project:zzzzzz"),
            mk("d", "old thing", scope="global", status="retracted"),
        ])
        self.ch = Chronicle(self.store, fake_embed, None)

    def test_record_for(self):
        text, entries = asyncio.run(self.ch.record_for("use tabs in python", self.tmp.name, []))
        ids = [e.id for e in entries]
        self.assertEqual(ids[0], "a")
        self.assertIn("b", ids)
        self.assertNotIn("c", ids)
        self.assertNotIn("d", ids)
        self.assertIn("[ACTIVE 0.90]", text)

    def test_no_embedding_falls_back_to_words(self):
        async def none_embed(texts):
            return [[] for _ in texts]

        async def broken_embed(texts):
            raise RuntimeError("no embedder")

        for emb in (none_embed, broken_embed):
            ch = Chronicle(self.store, emb, None)
            text, entries = asyncio.run(ch.record_for("use tabs in python", self.tmp.name, []))
            self.assertEqual([e.id for e in entries][:1], ["a"], emb.__name__)
            self.assertNotIn("c", [e.id for e in entries])
            self.assertNotIn("d", [e.id for e in entries])
            self.assertIn("tabs", text)

    def test_no_embedding_no_word_match_is_empty(self):
        async def none_embed(texts):
            return [[] for _ in texts]

        ch = Chronicle(self.store, none_embed, None)
        text, entries = asyncio.run(ch.record_for("zebra", self.tmp.name, []))
        self.assertEqual(entries, [])
        self.assertEqual(text, "(no prior record)")

    def test_record_empty(self):
        ch = Chronicle(FakeStore([]), fake_embed, None)
        text, entries = asyncio.run(ch.record_for("x", self.tmp.name, []))
        self.assertEqual(entries, [])
        self.assertEqual(text, "(no prior record)")

    def test_list(self):
        self.assertEqual(len(self.ch.list()), 4)
        ids = {e.id for e in self.ch.list(self.pid)}
        self.assertEqual(ids, {"a", "b", "d"})

    def test_pin_and_demote(self):
        e = self.ch.user_edit("b", {"pin": True}, 5.0)
        self.assertEqual((e.status, e.confidence), ("active", 1.0))
        self.assertEqual(e.evidence[-1].run_id, "user")
        self.assertEqual(e.last_confirmed_at, 5.0)
        self.assertEqual(self.store.entries["b"].status, "active")
        e = self.ch.user_edit("b", {"demote": True}, 6.0)
        self.assertEqual(e.status, "provisional")
        self.assertEqual(len(e.evidence), 2)

    def test_edit_statement_sets_active(self):
        e = self.ch.user_edit("b", {"statement": "tests live in t/"}, 1.0)
        self.assertEqual(e.statement, "tests live in t/")
        self.assertEqual(e.status, "active")
        self.assertIn("t/", e.evidence[-1].quote)

    def test_edit_missing(self):
        self.assertIsNone(self.ch.user_edit("nope", {"pin": True}, 1.0))

    def test_delete(self):
        self.assertTrue(self.ch.delete("a"))
        self.assertFalse(self.ch.delete("a"))
        self.assertNotIn("a", self.store.entries)

    def test_export_markdown(self):
        md = self.ch.export_markdown(self.pid)
        self.assertIn("## preference", md)
        self.assertIn("## project_fact", md)
        self.assertIn("[active 0.90] always use tabs in python files", md)
        self.assertNotIn("other project fact", md)
        self.assertLess(md.index("## preference"), md.index("## project_fact"))
        self.assertIn("(no entries)", Chronicle(FakeStore([]), fake_embed).export_markdown())


if __name__ == "__main__":
    unittest.main()
