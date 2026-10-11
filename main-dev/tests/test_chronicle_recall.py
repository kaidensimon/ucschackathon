import unittest

from council.chronicle.recall import (
    STATUS_WEIGHT,
    cosine,
    in_scope,
    keyword_embedding,
    rank,
    rank_text,
    render_record,
)
from council.core.schemas import ChronicleEntry


def E(id, status="active", scope="global", emb=None, conf=0.9, statement=None):
    return ChronicleEntry(
        id=id,
        status=status,
        scope=scope,
        embedding=emb or [],
        confidence=conf,
        statement=statement or f"statement {id}",
    )


class CosineTests(unittest.TestCase):
    def test_identical_and_orthogonal(self):
        self.assertAlmostEqual(cosine([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_empty_and_zero_return_zero(self):
        self.assertEqual(cosine([], []), 0.0)
        self.assertEqual(cosine([0.0, 0.0], [1.0, 1.0]), 0.0)
        self.assertEqual(cosine([1.0], [1.0, 2.0]), 0.0)


class ScopeTests(unittest.TestCase):
    def test_global_always(self):
        self.assertTrue(in_scope(E("a", scope="global"), None, []))
        self.assertTrue(in_scope(E("a", scope="global"), "p", ["x"]))

    def test_project_must_match(self):
        e = E("a", scope="project:abc")
        self.assertTrue(in_scope(e, "abc", []))
        self.assertFalse(in_scope(e, "other", []))
        self.assertFalse(in_scope(e, None, []))

    def test_category_must_be_listed(self):
        e = E("a", scope="category:coding")
        self.assertTrue(in_scope(e, None, ["coding", "math"]))
        self.assertFalse(in_scope(e, None, ["math"]))


class RankTests(unittest.TestCase):
    def test_status_weight_applied(self):
        q = [1.0, 0.0]
        entries = [
            E("prov", status="provisional", emb=[1.0, 0.0]),  # 0.6
            E("act", status="active", emb=[0.9, 0.1]),  # ~0.9 * 1.0
            E("cont", status="contested", emb=[1.0, 0.0]),  # 0.3
        ]
        out = rank(entries, q, None, [], k=8)
        self.assertEqual([e.id for e in out], ["act", "prov", "cont"])

    def test_superseded_and_retracted_excluded(self):
        q = [1.0]
        entries = [
            E("s", status="superseded", emb=[1.0]),
            E("r", status="retracted", emb=[1.0]),
            E("ok", status="active", emb=[1.0]),
        ]
        self.assertEqual([e.id for e in rank(entries, q, None, [])], ["ok"])

    def test_no_embedding_similarity_half(self):
        q = [1.0, 0.0]
        entries = [
            E("noemb", status="active"),  # 0.5 * 1.0
            E("weak", status="active", emb=[0.0, 1.0]),  # 0.0
        ]
        out = rank(entries, q, None, [])
        self.assertEqual([e.id for e in out], ["noemb", "weak"])

    def test_scope_filter_applied(self):
        q = [1.0]
        entries = [
            E("g", emb=[1.0]),
            E("p-other", scope="project:zzz", emb=[1.0]),
            E("p-mine", scope="project:abc", emb=[1.0]),
        ]
        ids = [e.id for e in rank(entries, q, "abc", [])]
        self.assertEqual(sorted(ids), ["g", "p-mine"])

    def test_k_limit(self):
        q = [1.0]
        entries = [E(str(i), emb=[1.0]) for i in range(12)]
        self.assertEqual(len(rank(entries, q, None, [])), 8)
        self.assertEqual(len(rank(entries, q, None, [], k=3)), 3)

    def test_empty_input(self):
        self.assertEqual(rank([], [1.0], None, []), [])


class RankTextTests(unittest.TestCase):
    def test_matches_by_words(self):
        es = [E("a", statement="Use tabs for indentation"), E("b", statement="Prefer sqlite for storage")]
        self.assertEqual([e.id for e in rank_text(es, "which indentation tabs", None, [])], ["a"])

    def test_no_word_overlap_returns_nothing(self):
        self.assertEqual(rank_text([E("a", statement="Use tabs")], "zebra", None, []), [])

    def test_scope_and_status_filters(self):
        es = [
            E("a", statement="tabs rule", scope="project:other"),
            E("b", statement="tabs rule", status="retracted"),
            E("c", statement="tabs rule", status="superseded"),
            E("d", statement="tabs rule", scope="project:p"),
        ]
        self.assertEqual([e.id for e in rank_text(es, "tabs", "p", [])], ["d"])

    def test_status_weight_breaks_equal_match(self):
        es = [E("a", statement="tabs rule", status="contested"), E("b", statement="tabs rule", status="active")]
        self.assertEqual([e.id for e in rank_text(es, "tabs", None, [])], ["b", "a"])

    def test_k_limits(self):
        es = [E(str(i), statement="tabs rule") for i in range(5)]
        self.assertEqual(len(rank_text(es, "tabs", None, [], k=2)), 2)
        self.assertEqual(rank_text(es, "tabs", None, [], k=0), [])


class RenderTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(render_record([]), "(no prior record)")

    def test_lines(self):
        out = render_record([E("a", status="active", conf=0.9, statement="Use tabs.")])
        self.assertEqual(out, "[ACTIVE 0.90] Use tabs.")
        two = render_record([E("a", statement="x"), E("b", status="contested", conf=0.4, statement="y")])
        self.assertEqual(two.splitlines(), ["[ACTIVE 0.90] x", "[CONTESTED 0.40] y"])


class KeywordEmbeddingTests(unittest.TestCase):
    def test_dim_and_determinism(self):
        v1 = keyword_embedding("the quick brown fox")
        v2 = keyword_embedding("The quick brown fox")
        self.assertEqual(len(v1), 64)
        self.assertEqual(v1, v2)

    def test_similar_text_closer(self):
        a = keyword_embedding("parse json file")
        b = keyword_embedding("parse the json file")
        c = keyword_embedding("paint a sunset")
        self.assertGreater(cosine(a, b), cosine(a, c))

    def test_empty_text_zero_vector(self):
        self.assertEqual(cosine(keyword_embedding(""), keyword_embedding("x")), 0.0)


class ConstantTests(unittest.TestCase):
    def test_weights(self):
        self.assertEqual(STATUS_WEIGHT, {"active": 1.0, "provisional": 0.6, "contested": 0.3})


if __name__ == "__main__":
    unittest.main()
