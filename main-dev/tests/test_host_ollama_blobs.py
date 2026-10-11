import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from council.host import ollama_blobs as B

DIGEST = "sha256:" + "ab" * 32


def put_manifest(root: Path, rel: str, digest: str = DIGEST, top: str = "manifests",
                 media: str = "application/vnd.ollama.image.model") -> Path:
    path = root / top / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schemaVersion": 2,
        "config": {"mediaType": "application/vnd.docker.container.image.v1+json",
                   "digest": "sha256:" + "00" * 32},
        "layers": [
            {"mediaType": "application/vnd.ollama.image.template", "digest": "sha256:" + "11" * 32},
            {"mediaType": media, "digest": digest},
            {"mediaType": "application/vnd.ollama.image.params", "digest": "sha256:" + "22" * 32},
        ],
    }), encoding="utf-8")
    return path


def put_blob(root: Path, digest: str = DIGEST) -> Path:
    blob = root / "blobs" / digest.replace(":", "-")
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"GGUF")
    return blob


class BlobTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_library_tag(self):
        put_manifest(self.root, "registry.ollama.ai/library/gemma3/12b")
        blob = put_blob(self.root)
        self.assertEqual(B.blob_for_tag("gemma3:12b", self.root), blob)

    def test_no_tag_means_latest(self):
        put_manifest(self.root, "registry.ollama.ai/library/phi4/latest")
        blob = put_blob(self.root)
        self.assertEqual(B.blob_for_tag("phi4", self.root), blob)
        self.assertEqual(B.blob_for_tag(" phi4:latest ", self.root), blob)

    def test_namespace(self):
        put_manifest(self.root, "registry.ollama.ai/someone/thing/q4")
        blob = put_blob(self.root)
        self.assertEqual(B.blob_for_tag("someone/thing:q4", self.root), blob)
        self.assertIsNone(B.blob_for_tag("thing:q4", self.root))

    def test_other_host(self):
        put_manifest(self.root, "hf.co/someone/thing-GGUF/Q4_K_M")
        blob = put_blob(self.root)
        self.assertEqual(B.blob_for_tag("hf.co/someone/thing-GGUF:Q4_K_M", self.root), blob)

    def test_manifests_v2(self):
        put_manifest(self.root, "registry.ollama.ai/library/qwen3/8b", top="manifests-v2")
        blob = put_blob(self.root)
        self.assertEqual(B.blob_for_tag("qwen3:8b", self.root), blob)

    def test_falls_through_to_v2_when_the_first_blob_is_gone(self):
        other = "sha256:" + "cd" * 32
        put_manifest(self.root, "registry.ollama.ai/library/qwen3/8b", digest=other)
        put_manifest(self.root, "registry.ollama.ai/library/qwen3/8b", top="manifests-v2")
        blob = put_blob(self.root)
        self.assertEqual(B.blob_for_tag("qwen3:8b", self.root), blob)

    def test_missing_things_give_none(self):
        self.assertIsNone(B.blob_for_tag("gemma3:12b", self.root))  # no manifest
        put_manifest(self.root, "registry.ollama.ai/library/gemma3/12b")
        self.assertIsNone(B.blob_for_tag("gemma3:12b", self.root))  # manifest, no blob
        self.assertIsNone(B.blob_for_tag("", self.root))
        self.assertIsNone(B.blob_for_tag("../../etc:passwd", self.root))
        self.assertIsNone(B.blob_for_tag("gemma3:12b", self.root / "nowhere"))

    def test_bad_manifests_give_none(self):
        put_blob(self.root)
        path = put_manifest(self.root, "registry.ollama.ai/library/a/1",
                            media="application/vnd.ollama.image.adapter")
        self.assertIsNone(B.blob_for_tag("a:1", self.root))  # no ".model" layer
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(B.blob_for_tag("a:1", self.root))
        path.write_text("[1, 2]", encoding="utf-8")
        self.assertIsNone(B.blob_for_tag("a:1", self.root))
        put_manifest(self.root, "registry.ollama.ai/library/a/1", digest="sha256:../../x")
        self.assertIsNone(B.blob_for_tag("a:1", self.root))

    def test_split_tag(self):
        self.assertEqual(B.split_tag("gemma3:12b"),
                         ("registry.ollama.ai", "library", "gemma3", "12b"))
        self.assertEqual(B.split_tag("u/n"), ("registry.ollama.ai", "u", "n", "latest"))
        self.assertEqual(B.split_tag("h.io/u/n:t"), ("h.io", "u", "n", "t"))
        self.assertIsNone(B.split_tag(":tag"))
        self.assertIsNone(B.split_tag("   "))


class DefaultDirTests(unittest.TestCase):
    def test_env_wins(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"OLLAMA_MODELS": d}):
            self.assertEqual(B.default_models_dir(), Path(d))

    def test_system_dir_when_it_exists(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(B, "SYSTEM_MODELS_DIR", d):
            os.environ.pop("OLLAMA_MODELS", None)
            self.assertEqual(B.default_models_dir(), Path(d))

    def test_home_otherwise(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(B, "SYSTEM_MODELS_DIR", str(Path(d) / "absent")):
            os.environ.pop("OLLAMA_MODELS", None)
            self.assertEqual(B.default_models_dir(), Path.home() / ".ollama" / "models")


class _E:
    def __init__(self, id, ollama_tag=None):
        self.id = id
        self.ollama_tag = ollama_tag


class ResolverTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_models_dir_from(self):
        self.assertEqual(B.models_dir_from(str(self.root)), self.root)
        with mock.patch.dict(os.environ, {"OLLAMA_MODELS": str(self.root)}):
            self.assertEqual(B.models_dir_from(""), self.root)
            self.assertEqual(B.models_dir_from(None), self.root)

    def test_resolver_finds_and_misses(self):
        put_manifest(self.root, "registry.ollama.ai/library/qwen/7b")
        blob = put_blob(self.root)
        find = B.resolver(self.root)
        self.assertEqual(find("qwen:7b"), blob)
        self.assertIsNone(find("absent:1"))

    def test_resolver_sees_a_later_pull(self):
        find = B.resolver(self.root)
        self.assertIsNone(find("qwen:7b"))
        put_manifest(self.root, "registry.ollama.ai/library/qwen/7b")
        blob = put_blob(self.root)
        self.assertEqual(find("qwen:7b"), blob)

    def test_resolver_default_dir(self):
        put_manifest(self.root, "registry.ollama.ai/library/qwen/7b")
        blob = put_blob(self.root)
        with mock.patch.dict(os.environ, {"OLLAMA_MODELS": str(self.root)}):
            self.assertEqual(B.resolver()("qwen:7b"), blob)

    def test_blob_map(self):
        put_manifest(self.root, "registry.ollama.ai/library/qwen/7b")
        blob = put_blob(self.root)
        reg = [_E("a", "qwen:7b"), _E("b", "absent:1"), _E("c", None), _E("d", "")]
        self.assertEqual(B.blob_map(reg, self.root), {"a": blob})
        self.assertEqual(B.blob_map([], self.root), {})


if __name__ == "__main__":
    unittest.main()
