import json
import unittest

from council.chamber.messages import (
    Card,
    CouncilMessage,
    LieMetric,
    TableAnswer,
    addressed_to,
    apply_card,
    card_schema,
    chat_view,
    clip,
    fallback_card,
    parse_card,
    table_view,
    tally,
    questions_to,
    transcript_text,
)

SEATS = ["s1", "s2", "s3", "s4", "s5", "s6"]
NAMES = {"s1": "Qwen", "s2": "Phi", "s3": "Gemma", "s4": "Llama", "s5": "Mistral", "s6": "Deepsk"}
LONG = "The cache must be invalidated on every write because stale reads break the ledger totals badly"


def msg(seat, rnd, text="text", to="all", card=None, lie=None, kind="reply", **kw):
    return CouncilMessage(
        turn_id=f"t-{seat}-{rnd}",
        seat_id=seat,
        seat_no=SEATS.index(seat),
        name=NAMES[seat],
        round=rnd,
        kind=kind,
        to=to,
        text=text,
        card=card,
        lie=lie,
        done=kw.pop("done", True),
        **kw,
    )


def card(note="short note", backs="new", to="all", stance="use a cache", conf=0.8):
    return Card(note=note, to=to, stance=stance, backs=backs, confidence=conf)


class TestClipAndTypes(unittest.TestCase):
    def test_clip_word_boundary(self):
        out = clip(LONG, 55)
        self.assertLessEqual(len(out), 55)
        self.assertTrue(LONG.startswith(out))
        self.assertEqual(LONG[len(out)], " ")

    def test_clip_short_unchanged(self):
        self.assertEqual(clip("  two   words ", 55), "two words")

    def test_clip_one_long_word(self):
        self.assertEqual(len(clip("x" * 80, 55)), 55)

    def test_card_always_55(self):
        c = Card(note=LONG, stance="s" * 300, confidence=7)
        self.assertLessEqual(len(c.note), 55)
        self.assertLessEqual(len(c.stance), 160)
        self.assertEqual(c.confidence, 1.0)
        self.assertEqual(c.to, "all")

    def test_card_empty_to_is_all(self):
        self.assertEqual(Card(note="n", stance="s", to=[]).to, "all")

    def test_lie_defaults(self):
        lie = LieMetric()
        self.assertIsNone(lie.score)
        self.assertEqual(lie.level, "ok")
        self.assertEqual(lie.reasons, [])


class TestCardSchema(unittest.TestCase):
    def test_enums_and_lengths(self):
        s = card_schema(["s2", "s3"], ["A1", "A2"])
        p = s["properties"]
        self.assertEqual(p["note"]["maxLength"], 55)
        self.assertEqual(p["stance"]["maxLength"], 160)
        self.assertEqual(p["backs"]["enum"], ["A1", "A2", "new"])
        self.assertEqual(p["to"]["anyOf"][0]["enum"], ["all"])
        self.assertEqual(p["to"]["anyOf"][1]["items"]["enum"], ["s2", "s3"])
        self.assertIn("backs", s["required"])
        json.dumps(s)

    def test_no_answers_no_seats(self):
        s = card_schema([], [])
        self.assertEqual(s["properties"]["backs"]["enum"], ["new"])
        self.assertEqual(s["properties"]["to"]["enum"], ["all"])


class TestParseCard(unittest.TestCase):
    def test_clean(self):
        c = parse_card(
            {"note": "cache it", "to": ["s2"], "stance": "use a cache", "backs": "A1",
             "confidence": 0.9, "changed": True, "changed_because": "Phi was right"},
            SEATS, ["A1", "A2"],
        )
        self.assertEqual((c.note, c.to, c.backs, c.confidence, c.changed), ("cache it", ["s2"], "A1", 0.9, True))
        self.assertEqual(c.changed_because, "Phi was right")

    def test_note_clipped_55(self):
        c = parse_card({"note": LONG, "stance": "x"}, SEATS, [])
        self.assertLessEqual(len(c.note), 55)
        self.assertFalse(c.note.endswith(" "))
        self.assertTrue(LONG.startswith(c.note))

    def test_unknown_ids(self):
        c = parse_card({"note": "n", "stance": "s", "to": ["zz", "S3", "s3"], "backs": "A9"}, SEATS, ["A1"])
        self.assertEqual(c.to, ["s3"])
        self.assertEqual(c.backs, "new")
        c = parse_card({"note": "n", "stance": "s", "to": ["zz"], "backs": "a1"}, SEATS, ["A1"])
        self.assertEqual(c.to, "all")
        self.assertEqual(c.backs, "A1")

    def test_to_as_string(self):
        self.assertEqual(parse_card({"note": "n", "stance": "s", "to": "all"}, SEATS, []).to, "all")
        self.assertEqual(parse_card({"note": "n", "stance": "s", "to": "s2, s4"}, SEATS, []).to, ["s2", "s4"])

    def test_confidence_clamped(self):
        f = lambda v: parse_card({"note": "n", "stance": "s", "confidence": v}, SEATS, []).confidence
        self.assertEqual(f(-3), 0.0)
        self.assertEqual(f(250), 1.0)
        self.assertAlmostEqual(f(80), 0.8)
        self.assertAlmostEqual(f("0.7"), 0.7)
        self.assertAlmostEqual(f("70%"), 0.7)
        self.assertEqual(f("high"), 0.5)
        self.assertEqual(f(None), 0.5)

    def test_string_input(self):
        raw = 'Here is the card:\n```json\n{"note": "ok", "stance": "yes", "backs": "A2"}\n```'
        c = parse_card(raw, SEATS, ["A1", "A2"])
        self.assertEqual((c.note, c.backs), ("ok", "A2"))

    def test_unusable(self):
        self.assertIsNone(parse_card(None, SEATS, []))
        self.assertIsNone(parse_card("not json", SEATS, []))
        self.assertIsNone(parse_card("[1, 2]", SEATS, []))
        self.assertIsNone(parse_card({}, SEATS, []))
        self.assertIsNone(parse_card({"note": "", "stance": None}, SEATS, []))

    def test_missing_note_or_stance(self):
        self.assertEqual(parse_card({"stance": "Use a cache. Then test."}, SEATS, []).note, "Use a cache.")
        self.assertEqual(parse_card({"note": "cache"}, SEATS, []).stance, "cache")


class TestFallbackCard(unittest.TestCase):
    def test_first_sentence(self):
        c = fallback_card("I back the cache. It is fast.\nMore words here.")
        self.assertEqual(c.note, "I back the cache.")
        self.assertEqual((c.to, c.backs), ("all", "new"))
        self.assertTrue(c.stance.startswith("I back the cache. It is fast."))

    def test_long_text(self):
        c = fallback_card(LONG + " and " + "word " * 100)
        self.assertLessEqual(len(c.note), 55)
        self.assertLessEqual(len(c.stance), 160)

    def test_empty(self):
        c = fallback_card("")
        self.assertTrue(c.note)
        self.assertEqual(c.backs, "new")


class TestTranscript(unittest.TestCase):
    def test_headers(self):
        ms = [
            msg("s1", 1, "Cache it.", card=card("cache it", "A2"), lie=LieMetric(score=0.72)),
            msg("s2", 2, "No.", to=["s1", "s3"], card=card("no cache", "A1", conf=0.9),
                lie=LieMetric(score=0.31, level="flag", reasons=["says 0.9 sure, reads 0.3"])),
            msg("s3", 2, "Hm."),
        ]
        t = transcript_text(ms)
        self.assertIn("[round 1] Qwen -> all   (lie detector: 0.72 ok)", t)
        self.assertIn("[round 2] Phi -> Qwen, Gemma   (lie detector: 0.31 FLAG: says 0.9 sure, reads 0.3)", t)
        self.assertIn("note: cache it | backs A2 | confidence 0.8", t)
        self.assertIn("(lie detector: n/a)", t)
        self.assertIn("Cache it.", t)

    def test_viewer_is_you(self):
        ms = [msg("s1", 1, "a"), msg("s2", 1, "b", to=["s1"])]
        t = transcript_text(ms, viewer_seat="s1")
        self.assertIn("[round 1] YOU -> all", t)
        self.assertIn("[round 1] Phi -> YOU", t)
        self.assertNotIn("Qwen", t)

    def test_card_to_used_when_message_to_all(self):
        ms = [msg("s1", 1, "a"), msg("s2", 1, "b", card=card(to=["s1"]))]
        self.assertIn("Phi -> Qwen", transcript_text(ms))

    def test_thinking_skipped_and_empty(self):
        self.assertEqual(transcript_text([]), "")
        self.assertEqual(transcript_text([msg("s1", 0, "", thinking=True, done=False)]), "")

    def test_compaction_keeps_last_round(self):
        ms = []
        for r in range(4):
            for s in SEATS:
                ms.append(msg(s, r, f"BODY{r} " + "word " * 200, card=card(f"note r{r}", "A1")))
        full = transcript_text(ms, max_chars=10**9)
        self.assertIn("BODY0", full)
        t = transcript_text(ms, max_chars=len(full) - 1)
        self.assertNotIn("BODY0", t)
        self.assertIn("BODY1", t)
        self.assertIn("[round 0] Qwen -> all", t)
        self.assertIn("note: note r0 | backs A1", t)
        tiny = transcript_text(ms, max_chars=10)
        for r in (0, 1, 2):
            self.assertNotIn(f"BODY{r}", tiny)
        self.assertEqual(tiny.count("BODY3"), 6)
        self.assertEqual(tiny.count("[round 0]"), 6)


class TestAddressedTo(unittest.TestCase):
    def test_unanswered_and_answered(self):
        ms = [
            msg("s2", 1, "Qwen, why?", to=["s1"]),
            msg("s3", 1, "everyone", to="all"),
            msg("s4", 1, "Qwen and Phi?", to=["s1", "s2"]),
            msg("s1", 2, "Phi: because.", to=["s2"]),
        ]
        got = addressed_to(ms, "s1", 0)
        self.assertEqual([m.seat_id for m in got], ["s4"])
        self.assertEqual([m.seat_id for m in addressed_to(ms, "s2", 0)], ["s4", "s1"])

    def test_all_reply_is_not_an_answer(self):
        ms = [msg("s2", 1, "?", to=["s1"]), msg("s1", 2, "hello", to="all")]
        self.assertEqual(len(addressed_to(ms, "s1", 0)), 1)

    def test_earlier_message_is_not_an_answer(self):
        ms = [msg("s1", 1, "hi", to=["s2"]), msg("s2", 1, "?", to=["s1"])]
        self.assertEqual([m.seat_id for m in addressed_to(ms, "s1", 0)], ["s2"])

    def test_since_round(self):
        ms = [msg("s2", 1, "?", to=["s1"]), msg("s3", 3, "?", to=["s1"])]
        self.assertEqual([m.seat_id for m in addressed_to(ms, "s1", 2)], ["s3"])

    def test_card_to_counts(self):
        ms = [msg("s2", 1, "?", card=card(to=["s1"])), msg("s1", 2, "ans", card=card(to=["s2"]))]
        self.assertEqual(addressed_to(ms, "s1", 0), [])


class TestQuestionsTo(unittest.TestCase):
    def test_all_named_messages_since_the_round_answered_or_not(self):
        ms = [
            msg("s1", 0, "old question", to=["s3"]),
            msg("s1", 1, "Gemma, show the step.", to=["s3"]),
            msg("s2", 1, "to everyone"),
            msg("s3", 1, "Qwen, here it is.", to=["s1"]),
            msg("s4", 1, "", to=["s3"]),
            msg("s4", 2, "Gemma, source that claim.", card=card(to=["s3"])),
        ]
        self.assertEqual([m.text for m in questions_to(ms, "s3", 1)],
                         ["Gemma, show the step.", "Gemma, source that claim."])
        self.assertEqual(len(questions_to(ms, "s3", 0)), 3)
        self.assertEqual(questions_to(ms, "s2", 0), [])


class TestViews(unittest.TestCase):
    def test_table_view_only_cards(self):
        ms = [
            msg("s1", 0, "long text " * 50, card=card("cache it", "A1"), lie=LieMetric(score=0.7)),
            msg("s2", 0, "other", card=card("no cache", "A2", to=["s1"])),
            msg("s1", 1, "", thinking=True, done=False),
            msg("s3", 1, "streaming", done=False),
        ]
        v = table_view(ms, SEATS)
        self.assertEqual(list(v), SEATS)
        self.assertEqual(set(v["s1"]), {"note", "thinking", "to", "backs", "lie", "round"})
        self.assertEqual(v["s1"]["note"], "cache it")
        self.assertTrue(v["s1"]["thinking"])
        self.assertEqual(v["s1"]["round"], 1)
        self.assertEqual(v["s1"]["lie"]["score"], 0.7)
        self.assertEqual(v["s1"]["backs"], "A1")
        self.assertEqual((v["s2"]["to"], v["s2"]["thinking"], v["s2"]["lie"]), (["s1"], False, None))
        self.assertEqual((v["s3"]["note"], v["s3"]["thinking"]), (None, True))
        self.assertEqual(v["s6"], {"note": None, "thinking": False, "to": None, "backs": None,
                                   "lie": None, "round": None})
        self.assertNotIn("long text", json.dumps(v))
        for seat in v.values():
            self.assertLessEqual(len(seat["note"] or ""), 55)

    def test_chat_view(self):
        ms = [msg("s1", 0, "full text", card=card(), lie=LieMetric(score=0.5, level="watch")),
              msg("s2", 0, "b", to=["s1"])]
        v = chat_view(ms)
        json.dumps(v)
        self.assertEqual([m["seat_id"] for m in v], ["s1", "s2"])
        self.assertEqual(v[0]["text"], "full text")
        self.assertEqual(v[0]["lie"]["level"], "watch")
        self.assertEqual(v[1]["to"], ["s1"])
        self.assertIsNone(v[1]["card"])


class TestVotes(unittest.TestCase):
    def test_apply_card_new_and_move(self):
        a = apply_card([], "s1", card(stance="cache"))
        self.assertEqual([(x.id, x.statement, x.proposed_by, x.seat_ids) for x in a],
                         [("A1", "cache", "s1", ["s1"])])
        b = apply_card(a, "s2", card(stance="no cache"))
        self.assertEqual([x.id for x in b], ["A1", "A2"])
        self.assertEqual(a[0].seat_ids, ["s1"])  # input untouched
        c = apply_card(b, "s2", card(backs="A1"))
        self.assertEqual([(x.id, x.seat_ids) for x in c], [("A1", ["s1", "s2"])])

    def test_apply_card_same_seat_twice(self):
        a = apply_card([], "s1", card(backs="A1", stance="cache"))
        a = apply_card(a, "s1", card(backs=a[0].id))
        self.assertEqual(a[0].seat_ids, ["s1"])

    def test_apply_card_new_same_words_no_churn(self):
        a = apply_card([], "s1", card(stance="Use a cache"))
        a = apply_card(a, "s1", card(stance="use a  cache"))
        self.assertEqual([(x.id, x.seat_ids) for x in a], [("A1", ["s1"])])

    def test_apply_card_new_id_after_removal(self):
        a = [TableAnswer(id="A1", statement="x", proposed_by="s1", seat_ids=["s1"]),
             TableAnswer(id="A3", statement="y", proposed_by="s2", seat_ids=["s2"])]
        b = apply_card(a, "s1", card(stance="z"))
        self.assertEqual([x.id for x in b], ["A3", "A4"])

    def test_tally_needed(self):
        for n, need in ((3, 3), (4, 4), (5, 4), (6, 5), (7, 6)):
            self.assertEqual(tally([], {}, n)["needed"], need)
        t = tally([], {}, 6)
        self.assertEqual((t["groups"], t["leading"], t["agree"], t["reached"]), ([], "", 0, False))
        self.assertEqual(tally([], {}, 10, threshold=0.7)["needed"], 7)

    def test_six_seat_debate(self):
        answers: list[TableAnswer] = []
        cards: dict[str, Card] = {}
        opening = {"s1": "cache", "s2": "no cache", "s3": "cache", "s4": "queue", "s5": "cache"}
        for seat, stance in opening.items():  # s6 gave no card
            cards[seat] = card(stance=stance)
            answers = apply_card(answers, seat, cards[seat])
        self.assertEqual([(a.id, a.seat_ids) for a in answers],
                         [("A1", ["s1", "s3", "s5"]), ("A2", ["s2"]), ("A3", ["s4"])])
        t = tally(answers, cards, 6)
        self.assertEqual((t["leading"], t["agree"], t["seats"], t["needed"], t["reached"]),
                         ("A1", 3, 6, 5, False))
        self.assertEqual(t["groups"][0], {"answer_id": "A1", "statement": "cache",
                                          "seat_ids": ["s1", "s3", "s5"]})
        self.assertEqual(len(t["groups"]), 3)
        json.dumps(t)

        for seat in ("s2", "s4"):
            cards[seat] = Card(note="moved", stance="cache", backs="A1", changed=True, changed_because="ok")
            answers = apply_card(answers, seat, cards[seat])
        self.assertEqual([a.id for a in answers], ["A1"])
        t = tally(answers, cards, 6)
        self.assertEqual((t["agree"], t["reached"]), (5, True))
        self.assertEqual(sorted(t["groups"][0]["seat_ids"]), ["s1", "s2", "s3", "s4", "s5"])

    def test_tally_ignores_seat_without_card(self):
        answers = [TableAnswer(id="A1", statement="x", proposed_by="s1", seat_ids=["s1", "s2"])]
        t = tally(answers, {"s1": card(backs="A1")}, 2)
        self.assertEqual((t["agree"], t["seats"], t["reached"]), (1, 2, False))

    def test_tally_tie_goes_to_first_answer(self):
        answers = [TableAnswer(id="A1", statement="x", proposed_by="s1", seat_ids=["s1"]),
                   TableAnswer(id="A2", statement="y", proposed_by="s2", seat_ids=["s2"])]
        t = tally(answers, {"s2": card(backs="A2"), "s1": card(backs="A1")}, 2)
        self.assertEqual(t["leading"], "A1")


class AnswerKeyTest(unittest.TestCase):
    def test_schema_field_only_for_keyed_types(self):
        from council.chamber import messages as m

        self.assertNotIn("answer_key", m.card_schema(["s1"], [])["properties"])
        self.assertNotIn("answer_key", m.card_schema(["s1"], [], "free")["properties"])
        for kind in m.KEYED_TYPES:
            schema = m.card_schema(["s1"], ["A1"], kind)
            self.assertIn("answer_key", schema["properties"])
            self.assertEqual(schema["required"][-1], "answer_key")
        self.assertEqual(m.card_schema([], [], "mcq")["properties"]["answer_key"]["maxLength"], 1)

    def test_parse_card_reads_the_key(self):
        from council.chamber import messages as m

        self.assertEqual(m.parse_card({"note": "n", "stance": "s", "answer_key": " B "}, [], []).answer_key, "B")
        self.assertEqual(m.parse_card({"note": "n", "stance": "s", "answer_key": 42}, [], []).answer_key, "42")
        self.assertEqual(m.parse_card({"note": "n", "stance": "s"}, [], []).answer_key, "")
        self.assertEqual(m.parse_card({"note": "n", "stance": "s", "answer_key": ["B"]}, [], []).answer_key, "")

    def test_last_answer_line_matches_the_solo_helper(self):
        from council.bench.solo import _last_answer_line
        from council.chamber import messages as m

        for text in ("work\nANSWER: B", "Answer: 3\nmore\n**ANSWER: 4**", "no line here", "", None):
            self.assertEqual(m.last_answer_line(text), _last_answer_line(text), text)


if __name__ == "__main__":
    unittest.main()
