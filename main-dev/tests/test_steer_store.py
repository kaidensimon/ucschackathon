import tempfile
import unittest
from pathlib import Path

from council.core.schemas_v15 import SteerCard
from council.steer.store import SteerStore, slug


def card(project="proj", model="qwen3:8b", version=1, active=False, **kw):
    return SteerCard(project=project, model_id=model, version=version, active=active,
                     layers=[14, 15], scale=0.5, examples=40, fraction=0.05,
                     reason="ok", trained_at=1.0, **kw)


class SteerStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.store = SteerStore(self.home)

    def test_slug_safe(self):
        self.assertEqual(slug("Qwen3:8B/x"), "qwen3_8b_x")
        for bad in ("", ".", ".."):
            s = slug(bad)
            self.assertTrue(s)
            self.assertNotIn(s, (".", ".."))

    def test_path_for_layout(self):
        p = self.store.path_for("My Proj", "qwen3:8b", 3)
        self.assertEqual(p, self.home / "steer" / "my_proj" / "qwen3_8b" / "v3.gguf")

    def test_next_version_empty_and_grows(self):
        self.assertEqual(self.store.next_version("proj", "m"), 1)
        self.store.save(card(model="m", version=1))
        self.assertEqual(self.store.next_version("proj", "m"), 2)
        # a gguf written before its card still reserves the number
        self.store.path_for("proj", "m", 5).parent.joinpath("v5.gguf").write_bytes(b"x")
        self.assertEqual(self.store.next_version("proj", "m"), 6)

    def test_save_fills_path_and_roundtrips(self):
        saved = self.store.save(card())
        self.assertEqual(saved.path, str(self.store.path_for("proj", "qwen3:8b", 1)))
        got = self.store.cards("proj")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].layers, [14, 15])
        self.assertEqual(got[0].scale, 0.5)

    def test_save_keeps_given_path(self):
        saved = self.store.save(card(path="/somewhere/v1.gguf"))
        self.assertEqual(saved.path, "/somewhere/v1.gguf")

    def test_save_does_not_mutate_input(self):
        c = card()
        self.store.save(c)
        self.assertEqual(c.path, "")

    def test_active_none_by_default(self):
        self.store.save(card())
        self.assertIsNone(self.store.active("proj", "qwen3:8b"))
        self.assertIsNone(self.store.active("proj", "never-seen"))

    def test_save_active_sets_active(self):
        self.store.save(card(version=1, active=True))
        a = self.store.active("proj", "qwen3:8b")
        self.assertIsNotNone(a)
        self.assertEqual(a.version, 1)
        self.assertTrue(a.active)

    def test_active_moves_to_newer_version(self):
        self.store.save(card(version=1, active=True))
        self.store.save(card(version=2, active=True))
        self.assertEqual(self.store.active("proj", "qwen3:8b").version, 2)
        flags = {c.version: c.active for c in self.store.cards("proj")}
        self.assertEqual(flags, {1: False, 2: True})

    def test_saving_inactive_over_active_clears_it(self):
        self.store.save(card(version=1, active=True))
        self.store.save(card(version=1, active=False))
        self.assertIsNone(self.store.active("proj", "qwen3:8b"))

    def test_saving_inactive_other_version_keeps_active(self):
        self.store.save(card(version=1, active=True))
        self.store.save(card(version=2, active=False))
        self.assertEqual(self.store.active("proj", "qwen3:8b").version, 1)

    def test_set_active_switch_and_off(self):
        self.store.save(card(version=1))
        self.store.save(card(version=2))
        self.assertTrue(self.store.set_active("proj", "qwen3:8b", 1))
        self.assertEqual(self.store.active("proj", "qwen3:8b").version, 1)
        self.assertTrue(self.store.set_active("proj", "qwen3:8b", 2))
        self.assertEqual(self.store.active("proj", "qwen3:8b").version, 2)
        self.assertTrue(self.store.set_active("proj", "qwen3:8b", None))
        self.assertIsNone(self.store.active("proj", "qwen3:8b"))

    def test_set_active_unknown(self):
        self.assertFalse(self.store.set_active("proj", "nope", 1))
        self.assertFalse(self.store.set_active("proj", "nope", None))
        self.store.save(card(version=1))
        self.assertFalse(self.store.set_active("proj", "qwen3:8b", 9))

    def test_cards_filter_and_order(self):
        self.store.save(card(project="b", model="m2", version=1))
        self.store.save(card(project="a", model="m1", version=2))
        self.store.save(card(project="a", model="m1", version=1))
        self.store.save(card(project="a", model="m0", version=1))
        all_ = self.store.cards()
        self.assertEqual([(c.project, c.model_id, c.version) for c in all_],
                         [("a", "m0", 1), ("a", "m1", 1), ("a", "m1", 2), ("b", "m2", 1)])
        self.assertEqual(len(self.store.cards("a")), 3)
        self.assertEqual(self.store.cards("zzz"), [])

    def test_cards_empty_home(self):
        self.assertEqual(self.store.cards(), [])

    def test_delete(self):
        self.store.save(card(version=1, active=True))
        self.store.save(card(model="other", version=1))
        self.assertTrue(self.store.delete("proj", "qwen3:8b"))
        self.assertIsNone(self.store.active("proj", "qwen3:8b"))
        self.assertEqual([c.model_id for c in self.store.cards("proj")], ["other"])
        self.assertFalse(self.store.delete("proj", "qwen3:8b"))

    def test_delete_last_model_removes_project_folder(self):
        self.store.save(card())
        self.assertTrue(self.store.delete("proj", "qwen3:8b"))
        self.assertFalse((self.home / "steer" / "proj").exists())

    def test_corrupt_files_skipped(self):
        self.store.save(card(version=1))
        folder = self.store.path_for("proj", "qwen3:8b", 1).parent
        (folder / "v2.json").write_text("{ not json", encoding="utf-8")
        (folder / "v3.json").write_text('{"project": "proj"}', encoding="utf-8")  # missing model_id
        (folder / "v4.json").write_bytes(b"\xff\xfe\x00bad")
        got = self.store.cards("proj")
        self.assertEqual([c.version for c in got], [1])
        # next version still steps past the corrupt ones
        self.assertEqual(self.store.next_version("proj", "qwen3:8b"), 5)

    def test_corrupt_active_file(self):
        self.store.save(card(version=1))
        folder = self.store.path_for("proj", "qwen3:8b", 1).parent
        (folder / "active.txt").write_text("banana", encoding="utf-8")
        self.assertIsNone(self.store.active("proj", "qwen3:8b"))
        self.assertEqual(len(self.store.cards("proj")), 1)
        self.assertFalse(self.store.cards("proj")[0].active)

    def test_active_points_at_corrupt_card(self):
        self.store.save(card(version=1, active=True))
        folder = self.store.path_for("proj", "qwen3:8b", 1).parent
        (folder / "v1.json").write_text("garbage", encoding="utf-8")
        self.assertIsNone(self.store.active("proj", "qwen3:8b"))

    def test_stray_files_ignored(self):
        self.store.save(card(version=1))
        (self.home / "steer" / "stray.txt").write_text("x", encoding="utf-8")
        (self.home / "steer" / "proj" / "notes.txt").write_text("x", encoding="utf-8")
        folder = self.store.path_for("proj", "qwen3:8b", 1).parent
        (folder / "readme.json").write_text("{}", encoding="utf-8")
        self.assertEqual(len(self.store.cards()), 1)

    def test_traversal_names_stay_inside_home(self):
        self.store.save(card(project="..", model=".."))
        steer_root = (self.home / "steer").resolve()
        for p in steer_root.rglob("*"):
            self.assertTrue(str(p.resolve()).startswith(str(steer_root)))
        self.assertEqual(len(self.store.cards("..")), 1)

    def test_projects_isolated_for_same_model(self):
        self.store.save(card(project="a", version=1, active=True))
        self.store.save(card(project="b", version=1))
        self.assertIsNotNone(self.store.active("a", "qwen3:8b"))
        self.assertIsNone(self.store.active("b", "qwen3:8b"))


if __name__ == "__main__":
    unittest.main()
