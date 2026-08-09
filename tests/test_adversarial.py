from __future__ import annotations
import unittest
from src.jitter_envelope import Envelope, JitterEnvelopeContract, Violation

class Adv(unittest.TestCase):
    def test_empty(self):
        env = Envelope(10, 5, 8, 3)
        r = JitterEnvelopeContract(env).check([])
        self.assertFalse(r.ok)
        self.assertEqual(r.violation, Violation.EMPTY)
    def test_flat_pass(self):
        env = Envelope(10, 5, 8, 3)
        r = JitterEnvelopeContract(env).check([1.0, 1.1, 1.2, 1.0, 1.05])
        self.assertTrue(r.ok)
        self.assertEqual(r.violation, Violation.NONE)
    def test_fingerprint_len(self):
        env = Envelope(10, 5, 8, 3)
        r = JitterEnvelopeContract(env).check([1.0, 2.0])
        self.assertEqual(len(r.fingerprint), 64)

if __name__ == "__main__":
    unittest.main()
