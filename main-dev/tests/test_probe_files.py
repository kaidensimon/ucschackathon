import tempfile
import unittest
from pathlib import Path

from council.core.schemas import Probe
from council.core.schemas_v15 import ProbeCard
from council.probe.probe_files import ProbeFiles, slug


def _probes(model_id: str) -> list[Probe]:
    return [
        Probe(model_id=model_id, layer=8, weights=[0.1, -0.2], bias=0.3, auroc=0.9, n_train=10),
        Probe(model_id=model_id, layer=12, weights=[0.5, 0.6], bias=-0.1, auroc=0.85, n_train=10),
    ]


class ProbeFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.pf = ProbeFiles(self.home)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_slug(self) -> None:
        self.assertEqual(slug("Qwen3:32B/Instruct"), "qwen3_32b_instruct")
        self.assertEqual(slug("a.b-c_d"), "a.b-c_d")
        self.assertNotIn("/", slug("../x"))
        self.assertNotEqual(slug(".."), "..")

    def test_save_assigns_versions(self) -> None:
        c1 = self.pf.save(ProbeCard(model_id="m:1", version=99), _probes("m:1"))
        c2 = self.pf.save(ProbeCard(model_id="m:1"), _probes("m:1"))
        self.assertEqual((c1.version, c2.version), (1, 2))
        self.assertTrue((self.home / "probes" / "m_1" / "v2.json").is_file())

    def test_roundtrip_with_platt(self) -> None:
        card = ProbeCard(model_id="m:1", layers=[8, 12], auroc=0.9, active=True)
        saved = self.pf.save(card, _probes("m:1"), platt=(1.5, -0.5), layout_version=3)
        got = self.pf.load("m:1")
        self.assertIsNotNone(got)
        c, probes, platt = got
        self.assertEqual(c.version, saved.version)
        self.assertEqual(c.layers, [8, 12])
        self.assertTrue(c.active)
        self.assertEqual(len(probes), 2)
        self.assertEqual(probes[1].weights, [0.5, 0.6])
        self.assertEqual(platt, (1.5, -0.5))
        self.assertEqual(self.pf.layout_version("m:1"), 3)

    def test_platt_none(self) -> None:
        self.pf.save(ProbeCard(model_id="m", active=True), _probes("m"))
        self.assertIsNone(self.pf.load("m")[2])

    def test_active_only_when_card_active(self) -> None:
        self.pf.save(ProbeCard(model_id="m", active=False), _probes("m"))
        self.assertFalse((self.home / "probes" / "m" / "active.txt").exists())
        self.assertIsNone(self.pf.load("m"))  # no active probe
        self.assertIsNotNone(self.pf.load("m", 1))  # explicit version still loads

    def test_load_missing(self) -> None:
        self.assertIsNone(self.pf.load("nope"))
        self.assertIsNone(self.pf.load("nope", 4))

    def test_active_follows_latest_active_save(self) -> None:
        self.pf.save(ProbeCard(model_id="m", active=True), _probes("m"))
        self.pf.save(ProbeCard(model_id="m", active=False), _probes("m"))
        self.assertEqual(self.pf.load("m")[0].version, 1)
        self.pf.save(ProbeCard(model_id="m", active=True), _probes("m"))
        self.assertEqual(self.pf.load("m")[0].version, 3)

    def test_cards_newest_per_model_with_active_flag(self) -> None:
        self.pf.save(ProbeCard(model_id="a", active=True), _probes("a"))
        self.pf.save(ProbeCard(model_id="a", active=False), _probes("a"))
        self.pf.save(ProbeCard(model_id="b", active=False), _probes("b"))
        cards = {c.model_id: c for c in self.pf.cards()}
        self.assertEqual(set(cards), {"a", "b"})
        self.assertEqual(cards["a"].version, 2)
        self.assertFalse(cards["a"].active)  # active.txt says 1
        self.assertFalse(cards["b"].active)
        self.pf.set_active("a", 2)
        cards = {c.model_id: c for c in self.pf.cards()}
        self.assertTrue(cards["a"].active)

    def test_cards_empty(self) -> None:
        self.assertEqual(self.pf.cards(), [])

    def test_set_active_and_clear(self) -> None:
        self.pf.save(ProbeCard(model_id="m"), _probes("m"))
        self.pf.save(ProbeCard(model_id="m"), _probes("m"))
        self.assertTrue(self.pf.set_active("m", 1))
        self.assertEqual(self.pf.load("m")[0].version, 1)
        self.assertTrue(self.pf.load("m")[0].active)
        self.assertFalse(self.pf.set_active("m", 9))
        self.assertTrue(self.pf.set_active("m", None))
        self.assertIsNone(self.pf.load("m"))
        self.assertTrue(self.pf.set_active("m", None))  # clearing twice is fine

    def test_delete(self) -> None:
        self.pf.save(ProbeCard(model_id="m", active=True), _probes("m"))
        self.assertTrue(self.pf.delete("m"))
        self.assertIsNone(self.pf.load("m"))
        self.assertEqual(self.pf.cards(), [])
        self.assertFalse(self.pf.delete("m"))

    def test_corrupt_version_skipped(self) -> None:
        self.pf.save(ProbeCard(model_id="m", active=True), _probes("m"))
        self.pf.save(ProbeCard(model_id="m", active=False), _probes("m"))
        d = self.home / "probes" / "m"
        (d / "v2.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.pf.load("m", 2))
        cards = self.pf.cards()
        self.assertEqual([c.version for c in cards], [1])  # falls back to v1
        self.assertTrue(cards[0].active)

    def test_corrupt_everything_never_raises(self) -> None:
        self.pf.save(ProbeCard(model_id="m", active=True), _probes("m"))
        d = self.home / "probes" / "m"
        (d / "v1.json").write_text('{"card": 5}', encoding="utf-8")
        (d / "active.txt").write_text("garbage", encoding="utf-8")
        self.assertIsNone(self.pf.load("m"))
        self.assertIsNone(self.pf.load("m", 1))
        self.assertEqual(self.pf.cards(), [])
        self.assertIsNone(self.pf.layout_version("m", 1))

    def test_no_temp_files_left(self) -> None:
        self.pf.save(ProbeCard(model_id="m", active=True), _probes("m"))
        names = sorted(p.name for p in (self.home / "probes" / "m").iterdir())
        self.assertEqual(names, ["active.txt", "v1.json"])

    def test_copy_between_machines(self) -> None:
        self.pf.save(ProbeCard(model_id="m:7", active=True, auroc=0.91), _probes("m:7"), platt=(2.0, 0.1))
        with tempfile.TemporaryDirectory() as other:
            import shutil

            shutil.copytree(self.home / "probes", Path(other) / "probes")
            got = ProbeFiles(Path(other)).load("m:7")
            self.assertIsNotNone(got)
            self.assertEqual(got[0].auroc, 0.91)
            self.assertEqual(got[2], (2.0, 0.1))


if __name__ == "__main__":
    unittest.main()
