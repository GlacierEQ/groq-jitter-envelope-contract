import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / "machine" / "excellence-state.json").read_text(encoding="utf-8"))
POSITION = json.loads((ROOT / "machine" / "canonical-position.json").read_text(encoding="utf-8"))
CAPABILITIES = json.loads((ROOT / "machine" / "capabilities.json").read_text(encoding="utf-8"))
RECEIPT = json.loads(
    (
        ROOT
        / "machine"
        / "evolution-receipts"
        / "2026-08-11-adaptive-multi-window-jitter.json"
    ).read_text(encoding="utf-8")
)

OLD_CURSOR = (
    "next:adaptive_multi_window_learning_change_point_detection_"
    "workload_class_profiles_hard_abort"
)
NEW_CURSOR = (
    "next:authenticated_latency_sample_provenance_model_freshness_"
    "restart_safe_profiles_and_distributed_regime_coordination"
)


class CanonicalPositionContractTests(unittest.TestCase):
    def test_evolving_state_is_gate_complete(self):
        self.assertEqual(STATE["principal_state"], "EVOLVING")
        self.assertEqual(STATE["state"], "EVOLVING")
        self.assertEqual(STATE["gates"]["CANONICAL_POSITION_RESOLVED"]["status"], "PASS")
        self.assertEqual(STATE["gates"]["EVOLUTION_CURSOR_DEFINED"]["status"], "PASS")
        self.assertEqual(STATE["canonical_position_ref"], "machine/canonical-position.json")

    def test_identity_and_lineage_are_preserved(self):
        self.assertEqual(POSITION["repository"], STATE["repository"])
        self.assertEqual(POSITION["canonical_identity"], "jitter-envelope-contract")
        policy = POSITION["integration_policy"]
        self.assertTrue(policy["preserve_repository_identity"])
        self.assertTrue(policy["preserve_lineage"])
        self.assertTrue(policy["presentation_independent"])
        self.assertTrue(policy["absorption_requires_functional_equivalence"])
        self.assertTrue(policy["absorption_requires_proof_equivalence"])

    def test_capabilities_preserve_legacy_names_and_add_adaptive_mechanisms(self):
        self.assertEqual(
            CAPABILITIES["capability_family"], "latency_shape_envelope_governance"
        )
        capabilities = set(CAPABILITIES["capabilities"])
        for legacy in {
            "multi-window-jitter-envelopes",
            "burst-latency-hard-limits",
            "plateau-drift-detection",
            "tail-latency-envelope-checking",
            "hard-envelope-abort-semantics",
            "deterministic-latency-violation-receipts",
        }:
            self.assertIn(legacy, capabilities)
        self.assertIn("per-workload-adaptive-jitter-profiles", capabilities)
        self.assertIn("change-point-hard-abort", capabilities)
        self.assertIn("rejected-window-baseline-preservation", capabilities)
        self.assertNotIn("hyper-scaling", capabilities)

    def test_evolution_is_consumed_and_next_boundary_is_material(self):
        self.assertEqual(RECEIPT["consumed_cursor"], OLD_CURSOR)
        self.assertEqual(STATE["evolution_history"][-1]["consumed_cursor"], OLD_CURSOR)
        self.assertEqual(STATE["evolution_cursor"], NEW_CURSOR)
        self.assertNotEqual(STATE["evolution_cursor"], OLD_CURSOR)
        self.assertIn("Authenticate latency-sample", POSITION["next_evolution"])
        self.assertIn("expire stale learned evidence", POSITION["next_evolution"])
        self.assertIn("coordinate regime state", POSITION["next_evolution"])
        self.assertIn("no Groq affiliation", POSITION["nonclaims"])
        self.assertIn("No Groq adoption", CAPABILITIES["truth_boundary"])


if __name__ == "__main__":
    unittest.main()
