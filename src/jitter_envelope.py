
"""Jitter envelope contract — latency shape gates."""
from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class Violation(str, Enum):
    NONE = "NONE"
    BURST_TOO_HIGH = "BURST_TOO_HIGH"
    PLATEAU_DRIFT = "PLATEAU_DRIFT"
    TAIL_TOO_HEAVY = "TAIL_TOO_HEAVY"
    EMPTY = "EMPTY"


def digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Envelope:
    """Milliseconds bounds for a fixed window of samples."""
    max_burst_ms: float  # max single sample
    max_median_ms: float
    max_p95_ms: float
    max_stdev_ms: float


@dataclass(frozen=True)
class EnvelopeReceipt:
    ok: bool
    violation: Violation
    median_ms: float | None
    p95_ms: float | None
    max_ms: float | None
    stdev_ms: float | None
    fingerprint: str


def _percentile(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


class JitterEnvelopeContract:
    def __init__(self, envelope: Envelope):
        self.envelope = envelope

    def check(self, samples_ms: Sequence[float]) -> EnvelopeReceipt:
        if not samples_ms:
            body = {"ok": False, "violation": Violation.EMPTY.value}
            return EnvelopeReceipt(False, Violation.EMPTY, None, None, None, None, digest(body))
        s = sorted(float(x) for x in samples_ms)
        med = statistics.median(s)
        p95 = _percentile(s, 0.95)
        mx = s[-1]
        sd = statistics.pstdev(s) if len(s) > 1 else 0.0
        v = Violation.NONE
        if mx > self.envelope.max_burst_ms:
            v = Violation.BURST_TOO_HIGH
        elif med > self.envelope.max_median_ms or sd > self.envelope.max_stdev_ms:
            v = Violation.PLATEAU_DRIFT
        elif p95 > self.envelope.max_p95_ms:
            v = Violation.TAIL_TOO_HEAVY
        ok = v is Violation.NONE
        body = {
            "ok": ok,
            "violation": v.value,
            "median": med,
            "p95": p95,
            "max": mx,
            "stdev": sd,
            "envelope": self.envelope.__dict__,
        }
        return EnvelopeReceipt(ok, v, med, p95, mx, sd, digest(body))
