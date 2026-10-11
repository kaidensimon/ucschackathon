"""End to end, mock mode: a review with split ballots argues once (review.debate), and when it
is still split after the fix cycles one random seat casts the final say (review.final_say),
the same seat for the same seed. Real RunPipeline, gateway, host, store; only the ballots are
scripted."""

import random
import unittest

from council.core import event_types as ET

try:  # "discover -s tests" imports the test modules top-level
    from test_api_run_pipeline import BUILD_TASK, SEATS, Base
    from test_api_run_pipeline_review import ACCEPT, FIX, install
except ImportError:  # "python -m unittest tests.test_..."
    from tests.test_api_run_pipeline import BUILD_TASK, SEATS, Base
    from tests.test_api_run_pipeline_review import ACCEPT, FIX, install


def split(phase, seat, cycle):
    """Three seats say fix, two accept, in the blind vote and in the argument round alike."""
    if phase == "final":
        return ACCEPT
    return FIX if seat < 3 else ACCEPT


class Debate(Base):
    async def _build(self, script, seed=3, **cfg):
        rig = self.rig
        for key, value in cfg.items():
            setattr(rig.config.review, key, value)
        tap = install(rig, script)
        run_id, result, ctl = await rig.run(
            BUILD_TASK, deliverable="build", options={"auto_delegate": True, "seed": seed})
        return run_id, result, ctl, tap

    async def test_split_vote_triggers_a_debate_round_before_any_verdict(self):
        run_id, _, _, tap = await self._build(split, debate=True, final_say="random_seat")
        rig = self.rig
        debate = rig.events(run_id, ET.REVIEW_DEBATE)
        self.assertGreaterEqual(len(debate), 1)
        first = debate[0].payload
        self.assertEqual(first["cycle"], 1)
        self.assertEqual(first["tally_before"]["fix"], 3)
        self.assertEqual(first["tally_before"]["accept"], 2)
        # every seat is called once blind and once in the argument round, per debated cycle
        for cycle in range(1, len(debate) + 1):
            blind = [s for ph, _, c, s in tap.calls if ph == "blind" and c == cycle]
            argued = [s for ph, _, c, s in tap.calls if ph == "debate" and c == cycle]
            self.assertEqual(len(blind), len(SEATS))
            self.assertEqual(len(argued), len(SEATS))
        types = [e.type for e in rig.events(run_id)]
        self.assertLess(types.index(ET.REVIEW_BALLOT), types.index(ET.REVIEW_DEBATE))
        self.assertLess(types.index(ET.REVIEW_DEBATE), types.index(ET.REVIEW_VERDICT))

    async def test_debate_that_moves_a_seat_shows_in_the_tally(self):
        def script(phase, seat, cycle):
            if phase == "blind":
                return FIX if seat >= 2 else ACCEPT  # 3 fix, 2 accept
            if phase == "debate":
                return ACCEPT if seat in (0, 1, 2) else FIX  # seat 2 is convinced: 3 accept, 2 fix
            return ACCEPT

        run_id, _, _, _ = await self._build(script, debate=True, final_say="random_seat")
        first = self.rig.events(run_id, ET.REVIEW_DEBATE)[0].payload
        self.assertEqual((first["tally_before"]["fix"], first["tally_before"]["accept"]), (3, 2))
        self.assertEqual((first["tally_after"]["fix"], first["tally_after"]["accept"]), (2, 3))

    async def test_still_split_after_the_cycles_one_random_seat_has_the_final_say(self):
        run_id, result, ctl, tap = await self._build(split, seed=3, debate=True, final_say="random_seat")
        rig = self.rig
        say = rig.events(run_id, ET.REVIEW_FINAL_SAY)
        self.assertEqual(len(say), 1)
        p = say[0].payload
        seats = rig.store.get_json("lineups", run_id)["seats"]
        want = random.Random(f"3:{p['cycle']}").choice(sorted(seats, key=lambda s: s["seat_no"]))
        self.assertEqual((p["seat_no"], p["model_id"]), (want["seat_no"], want["model_id"]))
        self.assertIn(p["model_id"], SEATS)
        # the debate happened in the cycle the final say closes, and before the final say
        debated = [e.payload["cycle"] for e in rig.events(run_id, ET.REVIEW_DEBATE)]
        self.assertIn(p["cycle"], debated)
        types = [e.type for e in rig.events(run_id)]
        self.assertLess(max(i for i, t in enumerate(types) if t == ET.REVIEW_DEBATE),
                        types.index(ET.REVIEW_FINAL_SAY))
        # exactly one deciding call, made to that seat, and nobody was asked
        finals = [(seat, s) for ph, seat, _, s in tap.calls if ph == "final"]
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0][1].model_id, want["model_id"])
        self.assertEqual(ctl.questions, [])
        self.assertEqual(p["verdict"], "accept")
        self.assertTrue(result.accepted)

    async def test_final_say_seat_is_deterministic_for_a_fixed_seed(self):
        run_id, _, _, _ = await self._build(split, seed=11, debate=True, final_say="random_seat")
        first = self.rig.events(run_id, ET.REVIEW_FINAL_SAY)[0].payload
        self.setUp()  # a fresh rig and store; the old one is closed at cleanup
        run_id2, _, _, _ = await self._build(split, seed=11, debate=True, final_say="random_seat")
        second = self.rig.events(run_id2, ET.REVIEW_FINAL_SAY)[0].payload
        self.assertEqual((first["cycle"], first["seat_no"], first["model_id"]),
                         (second["cycle"], second["seat_no"], second["model_id"]))

    async def test_other_seeds_can_pick_other_seats(self):
        picked = {}
        for seed in range(10):
            run_id, _, _, _ = await self._build(split, seed=seed, debate=True, final_say="random_seat")
            p = self.rig.events(run_id, ET.REVIEW_FINAL_SAY)[-1].payload
            seats = self.rig.store.get_json("lineups", run_id)["seats"]
            want = random.Random(f"{seed}:{p['cycle']}").choice(sorted(seats, key=lambda s: s["seat_no"]))
            self.assertEqual(p["seat_no"], want["seat_no"], f"seed {seed}")
            picked[seed] = p["seat_no"]
        self.assertGreater(len(set(picked.values())), 1)

    async def test_final_say_ballot_decides_the_work(self):
        def discard(phase, seat, cycle):
            return FIX if phase == "final" else split(phase, seat, cycle)

        run_id, result, _, _ = await self._build(discard, debate=True, final_say="random_seat")
        say = self.rig.events(run_id, ET.REVIEW_FINAL_SAY)
        self.assertEqual(len(say), 1)
        self.assertEqual(say[0].payload["verdict"], "fix")
        self.assertFalse(result.accepted)
        self.assertEqual(result.files_written, [])

    async def test_final_call_gets_the_record_of_every_cycle(self):
        run_id, _, _, tap = await self._build(split, debate=True, final_say="random_seat")
        cycle = self.rig.events(run_id, ET.REVIEW_FINAL_SAY)[0].payload["cycle"]
        spec = next(s for ph, _, _, s in tap.calls if ph == "final")
        text = spec.messages[-1]["content"]
        self.assertIn("one caveat is missing", text)
        self.assertEqual(spec.call_id.split(":")[-2], f"rvf{cycle}")
        for model_id in SEATS:
            self.assertNotIn(model_id, text)  # reviewers are letters, not model names


if __name__ == "__main__":
    unittest.main()
