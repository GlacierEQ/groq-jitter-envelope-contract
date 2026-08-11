from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "machine" / "excellence-state.json"
TARGET_PATH = ROOT / "machine" / "target-contract.json"
POSITION_PATH = ROOT / "machine" / "canonical-position.json"
RECEIPT_PATH = (
    ROOT
    / "machine"
    / "evolution-receipts"
    / "2026-08-11-adaptive-multi-window-jitter.json"
)

CONSUMED = (
    "next:adaptive_multi_window_learning_change_point_detection_"
    "workload_class_profiles_hard_abort"
)
NEXT = (
    "next:authenticated_latency_sample_provenance_model_freshness_"
    "restart_safe_profiles_and_distributed_regime_coordination"
)
CANDIDATE = "f523d013a75d49dcddf90b4f02762a2ce7f5ba26"
RUN = 31541043104


class EvolutionContractTests(unittest.TestCase):
    def load(self, path: Path) -> dict:
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn("<<<<<<<", raw)
        self.assertNotIn("=======", raw)
        self.assertNotIn(">>>>>>>", raw)
        return json.loads(raw)

    def test_receipt_is_bound_to_exact_candidate_proof(self):
        receipt = self.load(RECEIPT_PATH)
        self.assertEqual(receipt["repository"], "GlacierEQ/groq-jitter-envelope-contract")
        self.assertEqual(receipt["consumed_cursor"], CONSUMED)
        self.assertEqual(receipt["candidate_source_sha"], CANDIDATE)
        self.assertEqual(receipt["workflow_run"], RUN)
        self.assertEqual(receipt["python"], "PASS")
        self.assertEqual(receipt["native_c"], "PASS")
        self.assertEqual(receipt["next_cursor"], NEXT)

    def test_state_and_target_advance_together(self):
        state = self.load(STATE_PATH)
        target = self.load(TARGET_PATH)
        self.assertEqual(state["principal_state"], "EVOLVING")
        self.assertEqual(state["evolution_cursor"], NEXT)
        self.assertEqual(state["evolution_history"][-1]["candidate_source_sha"], CANDIDATE)
        self.assertEqual(state["evolution_history"][-1]["workflow_run"], RUN)
        self.assertEqual(target["identity"]["repository_id"], state["repository"])
        self.assertEqual(target["current"]["state"], "EVOLVING")
        self.assertEqual(target["proof"]["candidate_source_sha"], CANDIDATE)
        self.assertEqual(target["proof"]["workflow_run"], RUN)
        self.assertEqual(target["next_cursor"], NEXT)

    def test_claim_ceiling_keeps_unproved_authority_out(self):
        receipt = self.load(RECEIPT_PATH)
        position = self.load(POSITION_PATH)
        boundaries = " ".join(receipt["truth_boundaries"]).lower()
        self.assertIn("caller supplied", boundaries)
        self.assertIn("unauthenticated", boundaries)
        self.assertIn("not restart safe", boundaries)
        self.assertIn("not distributed", boundaries)
        nonclaims = " ".join(position["nonclaims"]).lower()
        self.assertIn("no groq affiliation", nonclaims)
        self.assertIn("caller supplied", nonclaims)
        self.assertIn("no restart-safe", nonclaims)


if __name__ == "__main__":
    unittest.main()
