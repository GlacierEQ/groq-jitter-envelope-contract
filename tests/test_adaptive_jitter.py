from __future__ import annotations

import math
import unittest

from src.jitter_envelope import (
    AdaptiveJitterEnvelopeContract,
    AdaptiveProfile,
    Envelope,
    Violation,
)


class AdaptiveJitterTests(unittest.TestCase):
    def profile(
        self,
        *,
        hard_burst: float = 20.0,
        hard_median: float = 15.0,
        hard_p95: float = 18.0,
        hard_stdev: float = 6.0,
        max_change_ratio: float = 0.30,
        adaptive_sigma: float = 4.0,
        min_margin_ms: float = 0.25,
    ) -> AdaptiveProfile:
        return AdaptiveProfile(
            hard_envelope=Envelope(
                max_burst_ms=hard_burst,
                max_median_ms=hard_median,
                max_p95_ms=hard_p95,
                max_stdev_ms=hard_stdev,
            ),
            min_windows=4,
            max_change_ratio=max_change_ratio,
            adaptive_sigma=adaptive_sigma,
            min_margin_ms=min_margin_ms,
        )

    def warm(
        self,
        contract: AdaptiveJitterEnvelopeContract,
        workload_class: str,
        value: float = 4.0,
    ) -> None:
        for _ in range(4):
            receipt = contract.check(workload_class, [value] * 20)
            self.assertTrue(receipt.ok)
            self.assertFalse(receipt.hard_abort)

    def test_change_point_hard_aborts_without_learning_bad_regime(self):
        contract = AdaptiveJitterEnvelopeContract({"interactive": self.profile()})
        self.warm(contract, "interactive")
        before = contract.snapshot("interactive")

        first = contract.check("interactive", [8.0] * 20)
        second = contract.check("interactive", [8.0] * 20)
        after = contract.snapshot("interactive")

        self.assertEqual(first.violation, Violation.CHANGE_POINT)
        self.assertTrue(first.hard_abort)
        self.assertEqual(first.windows_before, 4)
        self.assertEqual(first.windows_after, 4)
        self.assertGreater(first.change_score, 0.30)
        self.assertEqual(first, second)
        self.assertEqual(before, after)

    def test_workload_classes_learn_independently(self):
        contract = AdaptiveJitterEnvelopeContract(
            {
                "interactive": self.profile(),
                "bulk": self.profile(hard_median=25.0, hard_p95=28.0, hard_burst=30.0),
            }
        )
        self.warm(contract, "interactive", 4.0)
        self.warm(contract, "bulk", 10.0)

        interactive = contract.snapshot("interactive")
        bulk = contract.snapshot("bulk")
        self.assertAlmostEqual(interactive["slow_p95"], 4.0)
        self.assertAlmostEqual(bulk["slow_p95"], 10.0)

        bulk_receipt = contract.check("bulk", [11.0] * 20)
        self.assertTrue(bulk_receipt.ok)
        self.assertEqual(contract.snapshot("interactive"), interactive)

    def test_absolute_hard_envelope_remains_non_adaptive(self):
        contract = AdaptiveJitterEnvelopeContract({"interactive": self.profile()})
        self.warm(contract, "interactive")
        before = contract.snapshot("interactive")

        burst = contract.check("interactive", [4.0] * 19 + [50.0])
        self.assertEqual(burst.violation, Violation.BURST_TOO_HIGH)
        self.assertTrue(burst.hard_abort)
        self.assertEqual(contract.snapshot("interactive"), before)

    def test_learned_profile_breach_hard_aborts_when_change_threshold_is_loose(self):
        contract = AdaptiveJitterEnvelopeContract(
            {
                "interactive": self.profile(
                    max_change_ratio=10.0,
                    adaptive_sigma=1.0,
                    min_margin_ms=0.10,
                )
            }
        )
        self.warm(contract, "interactive")
        before = contract.snapshot("interactive")
        receipt = contract.check("interactive", [5.0] * 20)
        self.assertEqual(receipt.violation, Violation.ADAPTIVE_PROFILE_BREACH)
        self.assertTrue(receipt.hard_abort)
        self.assertEqual(contract.snapshot("interactive"), before)

    def test_unknown_empty_and_nonfinite_inputs_fail_closed(self):
        contract = AdaptiveJitterEnvelopeContract({"interactive": self.profile()})
        unknown = contract.check("missing", [4.0] * 10)
        self.assertEqual(unknown.violation, Violation.UNKNOWN_WORKLOAD_CLASS)
        self.assertTrue(unknown.hard_abort)

        empty = contract.check("interactive", [])
        self.assertEqual(empty.violation, Violation.EMPTY)
        self.assertTrue(empty.hard_abort)

        invalid = contract.check("interactive", [4.0, math.nan])
        self.assertEqual(invalid.violation, Violation.INVALID_SAMPLE)
        self.assertTrue(invalid.hard_abort)

    def test_snapshot_refuses_unknown_class(self):
        contract = AdaptiveJitterEnvelopeContract({"interactive": self.profile()})
        with self.assertRaises(ValueError):
            contract.snapshot("missing")


if __name__ == "__main__":
    unittest.main()
