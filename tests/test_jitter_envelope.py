
from __future__ import annotations
import unittest
from src.jitter_envelope import Envelope, JitterEnvelopeContract, Violation

class JitterTests(unittest.TestCase):
    def test_pass_flat(self):
        env = Envelope(max_burst_ms=10, max_median_ms=5, max_p95_ms=8, max_stdev_ms=2)
        r = JitterEnvelopeContract(env).check([4, 4.2, 3.8, 4.1, 4.0] * 5)
        self.assertTrue(r.ok)

    def test_burst(self):
        env = Envelope(max_burst_ms=10, max_median_ms=5, max_p95_ms=8, max_stdev_ms=3)
        r = JitterEnvelopeContract(env).check([4] * 20 + [50])
        self.assertEqual(r.violation, Violation.BURST_TOO_HIGH)

if __name__ == "__main__":
    unittest.main()
