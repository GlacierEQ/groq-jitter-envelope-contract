#!/usr/bin/env python3
"""Cold-start: JitterEnvelopeContract burst violation."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jitter_envelope import Envelope, JitterEnvelopeContract, Violation

def main() -> int:
    env = Envelope(max_burst_ms=10.0, max_median_ms=5.0, max_p95_ms=8.0, max_stdev_ms=3.0)
    r = JitterEnvelopeContract(env).check([1.0, 2.0, 3.0, 50.0])
    out = {
        "ok_flag": r.ok,
        "violation": r.violation.value,
        "expected_violation": Violation.BURST_TOO_HIGH.value,
        "max_ms": r.max_ms,
        "fingerprint": r.fingerprint,
        "ok": (not r.ok) and r.violation is Violation.BURST_TOO_HIGH,
    }
    print(json.dumps(out, sort_keys=True))
    return 0 if out["ok"] else 1
if __name__ == "__main__":
    raise SystemExit(main())
