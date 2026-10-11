import unittest
from unittest import mock

from council.core.schemas import TelemetrySnapshot
from council.telemetry import sampler as sm
from council.telemetry.sampler import FakeSampler, Sampler, default_gpu_reader

GIB_KB = 1024 * 1024
MEM = {
    "MemTotal": 128 * GIB_KB,
    "MemAvailable": 38 * GIB_KB,
    "SwapTotal": 8 * GIB_KB,
    "SwapFree": 6 * GIB_KB,
}


class SamplerTests(unittest.TestCase):
    def test_memory(self):
        s = Sampler(lambda: MEM).sample()
        self.assertIsInstance(s, TelemetrySnapshot)
        self.assertAlmostEqual(s.mem_total_gib, 128.0)
        self.assertAlmostEqual(s.mem_available_gib, 38.0)
        self.assertAlmostEqual(s.mem_used_gib, 90.0)
        self.assertAlmostEqual(s.swap_used_gib, 2.0)
        self.assertIsNone(s.gpu_util)

    def test_full(self):
        gw = lambda: {
            "tps_by_model": {"a": 100.0, "b": 50.0},
            "in_flight": {"a": 2},
            "queue_depth": 3,
            "tokens_in": 1_000_000,
            "tokens_out": 500_000,
            "tokens_reasoning": 500_000,
        }
        host = lambda: [{"model_id": "a", "footprint_gib": 20.5}]
        gpu = lambda: {"gpu_util": 80.0, "gpu_temp_c": 60.0, "gpu_power_w": 150.0}
        s = Sampler(lambda: MEM, gw, host, gpu, reference_price_per_mtok=2.0).sample()
        self.assertEqual(s.resident[0].model_id, "a")
        self.assertAlmostEqual(s.resident[0].footprint_gib, 20.5)
        self.assertAlmostEqual(s.tps_total, 150.0)
        self.assertEqual(s.in_flight, {"a": 2})
        self.assertEqual(s.queue_depth, 3)
        self.assertEqual(s.gpu_util, 80.0)
        self.assertEqual(s.gpu_power_w, 150.0)
        self.assertAlmostEqual(s.cloud_equiv_usd, 4.0)

    def test_gpu_none(self):
        s = Sampler(lambda: MEM, gpu_reader=lambda: None).sample()
        self.assertIsNone(s.gpu_temp_c)

    def test_default_gpu_reader(self):
        ok = mock.Mock(returncode=0, stdout="37, 55, 210.5\n")
        with mock.patch.object(sm.subprocess, "run", return_value=ok) as run:
            r = default_gpu_reader()
            self.assertEqual(run.call_args.kwargs["timeout"], 2)
        self.assertEqual(r, {"gpu_util": 37.0, "gpu_temp_c": 55.0, "gpu_power_w": 210.5})

    def test_default_gpu_reader_failures(self):
        with mock.patch.object(sm.subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(default_gpu_reader())
        bad = mock.Mock(returncode=1, stdout="")
        with mock.patch.object(sm.subprocess, "run", return_value=bad):
            self.assertIsNone(default_gpu_reader())
        junk = mock.Mock(returncode=0, stdout="N/A, N/A, N/A")
        with mock.patch.object(sm.subprocess, "run", return_value=junk):
            self.assertIsNone(default_gpu_reader())


class FakeSamplerTests(unittest.TestCase):
    def test_ranges(self):
        f = FakeSampler(seed=1)
        for level in (0.0, 0.5, 1.0):
            f.set_activity(level)
            s = f.sample()
            self.assertEqual(len(s.resident), 6)
            self.assertTrue(85 <= s.mem_used_gib <= 95)
            self.assertAlmostEqual(s.mem_total_gib, 128.0)
            self.assertTrue(150 <= s.tps_total <= 420)

    def test_activity_moves_tps(self):
        f = FakeSampler(seed=2)
        f.set_activity(0.0)
        lo = f.sample().tps_total
        f.set_activity(1.0)
        hi = f.sample().tps_total
        self.assertGreater(hi, lo)

    def test_smooth(self):
        f = FakeSampler(seed=3)
        a = f.sample().tps_total
        b = f.sample().tps_total
        self.assertLess(abs(a - b), 30)


if __name__ == "__main__":
    unittest.main()
