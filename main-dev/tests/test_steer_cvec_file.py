import struct
import tempfile
import unittest
from pathlib import Path

from council.steer import cvec_file as C


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


class TestCvecFile(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.dir = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()

    def test_round_trip(self):
        dirs = {14: [0.5, -1.25, 3.0], 15: [0.0, 1.5, -2.5]}
        p = C.write_cvec(self.dir / "a" / "b" / "v.gguf", dirs, "granite")
        self.assertTrue(p.exists())
        self.assertEqual(C.read_cvec(p), dirs)

    def test_round_trip_rounds_to_f32(self):
        p = C.write_cvec(self.dir / "v.gguf", {3: [0.1, 0.2]})
        self.assertEqual(C.read_cvec(p), {3: [f32(0.1), f32(0.2)]})

    def test_header_and_alignment(self):
        p = C.write_cvec(self.dir / "v.gguf", {2: [1.0] * 5, 1: [2.0] * 7}, "h")
        buf = p.read_bytes()
        self.assertEqual(buf[:4], b"GGUF")
        self.assertEqual(struct.unpack_from("<IQQ", buf, 4), (3, 2, 3))
        r = C._Reader(buf)
        r.pos = 4
        _, n_t, n_kv = r.take("<IQQ")
        for _ in range(n_kv):
            r.string()
            (typ,) = r.take("<I")
            if typ == 8:
                r.string()
            else:
                r.take("<i")
        for _ in range(n_t):
            r.string()
            r.take("<IQIQ")
        base = r.pos + ((-r.pos) % 32)
        self.assertEqual(base % 32, 0)
        self.assertEqual((len(buf) - base) % 32, 0)
        self.assertEqual(buf[r.pos:base], b"\0" * (base - r.pos))

    def test_layer_order(self):
        p = C.write_cvec(self.dir / "v.gguf", {9: [9.0], 2: [2.0], 5: [5.0]})
        self.assertEqual(list(C.read_cvec(p)), [2, 5, 9])
        buf = p.read_bytes()
        self.assertLess(buf.index(b"direction.2"), buf.index(b"direction.5"))
        self.assertLess(buf.index(b"direction.5"), buf.index(b"direction.9"))

    def test_atomic_no_temp_left(self):
        C.write_cvec(self.dir / "v.gguf", {0: [1.0]})
        C.write_cvec(self.dir / "v.gguf", {0: [2.0]})
        self.assertEqual([x.name for x in self.dir.iterdir()], ["v.gguf"])
        self.assertEqual(C.read_cvec(self.dir / "v.gguf"), {0: [2.0]})

    def test_empty_directions(self):
        p = C.write_cvec(self.dir / "v.gguf", {})
        self.assertEqual(C.read_cvec(p), {})

    def test_bad_magic(self):
        p = self.dir / "bad.gguf"
        p.write_bytes(b"NOPE" + b"\0" * 64)
        with self.assertRaises(ValueError):
            C.read_cvec(p)

    def test_truncated_and_missing(self):
        good = C.write_cvec(self.dir / "v.gguf", {1: [1.0, 2.0, 3.0]}).read_bytes()
        for cut in (3, 10, 40, len(good) - 40):
            p = self.dir / "t.gguf"
            p.write_bytes(good[:cut])
            with self.assertRaises(ValueError, msg=str(cut)):
                C.read_cvec(p)
        with self.assertRaises(ValueError):
            C.read_cvec(self.dir / "missing.gguf")

    def test_wrong_architecture(self):
        p = C.write_cvec(self.dir / "v.gguf", {1: [1.0]})
        p.write_bytes(p.read_bytes().replace(b"controlvector", b"controlvectox", 1))
        with self.assertRaises(ValueError):
            C.read_cvec(p)

    def test_scaled_arg(self):
        p = self.dir / "v.gguf"
        self.assertEqual(C.scaled_arg(p, 0.5), f"{p}:0.5")
        self.assertEqual(C.scaled_arg(p, -1.0), f"{p}:-1")


if __name__ == "__main__":
    unittest.main()
