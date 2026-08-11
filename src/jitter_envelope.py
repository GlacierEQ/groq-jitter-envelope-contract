"""Jitter envelope contracts for deterministic latency-shape refusal."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class Violation(str, Enum):
    NONE = "NONE"
    BURST_TOO_HIGH = "BURST_TOO_HIGH"
    PLATEAU_DRIFT = "PLATEAU_DRIFT"
    TAIL_TOO_HEAVY = "TAIL_TOO_HEAVY"
    EMPTY = "EMPTY"
    INVALID_SAMPLE = "INVALID_SAMPLE"
    UNKNOWN_WORKLOAD_CLASS = "UNKNOWN_WORKLOAD_CLASS"
    CHANGE_POINT = "CHANGE_POINT"
    ADAPTIVE_PROFILE_BREACH = "ADAPTIVE_PROFILE_BREACH"


def digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Envelope:
    """Milliseconds bounds for a fixed window of samples."""

    max_burst_ms: float
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
    """Legacy fixed-window contract preserved for existing callers."""

    def __init__(self, envelope: Envelope):
        self.envelope = envelope

    def check(self, samples_ms: Sequence[float]) -> EnvelopeReceipt:
        if not samples_ms:
            body = {"ok": False, "violation": Violation.EMPTY.value}
            return EnvelopeReceipt(
                False, Violation.EMPTY, None, None, None, None, digest(body)
            )
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


@dataclass(frozen=True)
class AdaptiveProfile:
    """One workload class' immutable hard limits and bounded learning policy."""

    hard_envelope: Envelope
    min_windows: int = 4
    alpha_fast: float = 0.50
    alpha_slow: float = 0.10
    alpha_deviation: float = 0.25
    max_change_ratio: float = 0.45
    adaptive_sigma: float = 4.0
    min_margin_ms: float = 0.25

    def __post_init__(self) -> None:
        limits = self.hard_envelope.__dict__.values()
        if any(not math.isfinite(v) or v <= 0 for v in limits):
            raise ValueError("hard envelope limits must be finite and positive")
        if self.min_windows < 1:
            raise ValueError("min_windows must be positive")
        if not 0 < self.alpha_slow <= self.alpha_fast <= 1:
            raise ValueError("learning rates must satisfy 0 < slow <= fast <= 1")
        if not 0 < self.alpha_deviation <= 1:
            raise ValueError("alpha_deviation must be in (0, 1]")
        if not math.isfinite(self.max_change_ratio) or self.max_change_ratio <= 0:
            raise ValueError("max_change_ratio must be finite and positive")
        if not math.isfinite(self.adaptive_sigma) or self.adaptive_sigma <= 0:
            raise ValueError("adaptive_sigma must be finite and positive")
        if not math.isfinite(self.min_margin_ms) or self.min_margin_ms <= 0:
            raise ValueError("min_margin_ms must be finite and positive")


@dataclass
class _ProfileState:
    windows: int = 0
    fast_median: float = 0.0
    slow_median: float = 0.0
    dev_median: float = 0.0
    fast_p95: float = 0.0
    slow_p95: float = 0.0
    dev_p95: float = 0.0
    fast_stdev: float = 0.0
    slow_stdev: float = 0.0
    dev_stdev: float = 0.0


@dataclass(frozen=True)
class AdaptiveEnvelopeReceipt:
    ok: bool
    hard_abort: bool
    violation: Violation
    workload_class: str
    windows_before: int
    windows_after: int
    median_ms: float | None
    p95_ms: float | None
    max_ms: float | None
    stdev_ms: float | None
    change_score: float
    learned_median_limit_ms: float | None
    learned_p95_limit_ms: float | None
    learned_stdev_limit_ms: float | None
    fingerprint: str


class AdaptiveJitterEnvelopeContract:
    """Bounded multi-window learning with class isolation and hard abort.

    Every sample window must first satisfy its immutable hard envelope. Passing
    windows then update independent fast/slow EWMAs for that workload class.
    Once the class has enough history, a regime change or learned-profile breach
    aborts the window and *does not* contaminate the learned baseline.
    """

    def __init__(self, profiles: Mapping[str, AdaptiveProfile]):
        if not profiles:
            raise ValueError("at least one workload profile is required")
        if any(not isinstance(name, str) or not name.strip() for name in profiles):
            raise ValueError("workload class names must be non-empty strings")
        self._profiles = dict(profiles)
        self._states = {name: _ProfileState() for name in profiles}

    def snapshot(self, workload_class: str) -> dict[str, float | int]:
        profile = self._profiles.get(workload_class)
        if profile is None:
            raise ValueError("unknown workload class")
        state = self._states[workload_class]
        return {
            "windows": state.windows,
            "fast_median": state.fast_median,
            "slow_median": state.slow_median,
            "fast_p95": state.fast_p95,
            "slow_p95": state.slow_p95,
            "fast_stdev": state.fast_stdev,
            "slow_stdev": state.slow_stdev,
            "learned_median_limit_ms": self._limit(
                state.slow_median, state.dev_median, profile
            ),
            "learned_p95_limit_ms": self._limit(
                state.slow_p95, state.dev_p95, profile
            ),
            "learned_stdev_limit_ms": self._limit(
                state.slow_stdev, state.dev_stdev, profile
            ),
        }

    def check(
        self, workload_class: str, samples_ms: Sequence[float]
    ) -> AdaptiveEnvelopeReceipt:
        profile = self._profiles.get(workload_class)
        if profile is None:
            return self._receipt(
                workload_class,
                Violation.UNKNOWN_WORKLOAD_CLASS,
                0,
                0,
                None,
                0.0,
                None,
            )

        state = self._states[workload_class]
        windows_before = state.windows
        if not samples_ms or any(
            not math.isfinite(float(value)) or float(value) < 0
            for value in samples_ms
        ):
            violation = Violation.EMPTY if not samples_ms else Violation.INVALID_SAMPLE
            return self._receipt(
                workload_class,
                violation,
                windows_before,
                windows_before,
                None,
                0.0,
                None,
            )

        fixed = JitterEnvelopeContract(profile.hard_envelope).check(samples_ms)
        if not fixed.ok:
            return self._receipt(
                workload_class,
                fixed.violation,
                windows_before,
                windows_before,
                fixed,
                0.0,
                self._limits(state, profile),
            )

        assert fixed.median_ms is not None
        assert fixed.p95_ms is not None
        assert fixed.stdev_ms is not None
        metrics = (fixed.median_ms, fixed.p95_ms, fixed.stdev_ms)

        if state.windows == 0:
            prospective = metrics
            change_score = 0.0
        else:
            prospective = (
                self._ewma(state.fast_median, metrics[0], profile.alpha_fast),
                self._ewma(state.fast_p95, metrics[1], profile.alpha_fast),
                self._ewma(state.fast_stdev, metrics[2], profile.alpha_fast),
            )
            change_score = max(
                self._ratio(prospective[0], state.slow_median),
                self._ratio(prospective[1], state.slow_p95),
                self._ratio(prospective[2], state.slow_stdev),
            )

        limits = self._limits(state, profile)
        warmed = state.windows >= profile.min_windows
        if warmed and change_score > profile.max_change_ratio:
            return self._receipt(
                workload_class,
                Violation.CHANGE_POINT,
                windows_before,
                windows_before,
                fixed,
                change_score,
                limits,
            )

        if warmed and limits is not None:
            median_limit, p95_limit, stdev_limit = limits
            if (
                metrics[0] > median_limit
                or metrics[1] > p95_limit
                or metrics[2] > stdev_limit
            ):
                return self._receipt(
                    workload_class,
                    Violation.ADAPTIVE_PROFILE_BREACH,
                    windows_before,
                    windows_before,
                    fixed,
                    change_score,
                    limits,
                )

        self._learn(state, metrics, profile)
        return self._receipt(
            workload_class,
            Violation.NONE,
            windows_before,
            state.windows,
            fixed,
            change_score,
            self._limits(state, profile),
        )

    def _learn(
        self,
        state: _ProfileState,
        metrics: tuple[float, float, float],
        profile: AdaptiveProfile,
    ) -> None:
        median, p95, stdev = metrics
        if state.windows == 0:
            state.fast_median = state.slow_median = median
            state.fast_p95 = state.slow_p95 = p95
            state.fast_stdev = state.slow_stdev = stdev
            state.windows = 1
            return

        old_slow_median = state.slow_median
        old_slow_p95 = state.slow_p95
        old_slow_stdev = state.slow_stdev
        state.fast_median = self._ewma(
            state.fast_median, median, profile.alpha_fast
        )
        state.fast_p95 = self._ewma(state.fast_p95, p95, profile.alpha_fast)
        state.fast_stdev = self._ewma(
            state.fast_stdev, stdev, profile.alpha_fast
        )
        state.slow_median = self._ewma(
            state.slow_median, median, profile.alpha_slow
        )
        state.slow_p95 = self._ewma(state.slow_p95, p95, profile.alpha_slow)
        state.slow_stdev = self._ewma(
            state.slow_stdev, stdev, profile.alpha_slow
        )
        state.dev_median = self._ewma(
            state.dev_median,
            abs(median - old_slow_median),
            profile.alpha_deviation,
        )
        state.dev_p95 = self._ewma(
            state.dev_p95, abs(p95 - old_slow_p95), profile.alpha_deviation
        )
        state.dev_stdev = self._ewma(
            state.dev_stdev,
            abs(stdev - old_slow_stdev),
            profile.alpha_deviation,
        )
        state.windows += 1

    @staticmethod
    def _ewma(previous: float, value: float, alpha: float) -> float:
        return previous + alpha * (value - previous)

    @staticmethod
    def _ratio(value: float, baseline: float) -> float:
        return abs(value - baseline) / max(abs(baseline), 0.25)

    @staticmethod
    def _limit(baseline: float, deviation: float, profile: AdaptiveProfile) -> float:
        return baseline + profile.adaptive_sigma * max(
            deviation, profile.min_margin_ms
        )

    def _limits(
        self, state: _ProfileState, profile: AdaptiveProfile
    ) -> tuple[float, float, float] | None:
        if state.windows == 0:
            return None
        return (
            self._limit(state.slow_median, state.dev_median, profile),
            self._limit(state.slow_p95, state.dev_p95, profile),
            self._limit(state.slow_stdev, state.dev_stdev, profile),
        )

    def _receipt(
        self,
        workload_class: str,
        violation: Violation,
        windows_before: int,
        windows_after: int,
        fixed: EnvelopeReceipt | None,
        change_score: float,
        limits: tuple[float, float, float] | None,
    ) -> AdaptiveEnvelopeReceipt:
        values = (
            (fixed.median_ms, fixed.p95_ms, fixed.max_ms, fixed.stdev_ms)
            if fixed is not None
            else (None, None, None, None)
        )
        learned = limits or (None, None, None)
        ok = violation is Violation.NONE
        body = {
            "ok": ok,
            "hard_abort": not ok,
            "violation": violation.value,
            "workload_class": workload_class,
            "windows_before": windows_before,
            "windows_after": windows_after,
            "median_ms": values[0],
            "p95_ms": values[1],
            "max_ms": values[2],
            "stdev_ms": values[3],
            "change_score": change_score,
            "learned_median_limit_ms": learned[0],
            "learned_p95_limit_ms": learned[1],
            "learned_stdev_limit_ms": learned[2],
        }
        return AdaptiveEnvelopeReceipt(
            ok=ok,
            hard_abort=not ok,
            violation=violation,
            workload_class=workload_class,
            windows_before=windows_before,
            windows_after=windows_after,
            median_ms=values[0],
            p95_ms=values[1],
            max_ms=values[2],
            stdev_ms=values[3],
            change_score=change_score,
            learned_median_limit_ms=learned[0],
            learned_p95_limit_ms=learned[1],
            learned_stdev_limit_ms=learned[2],
            fingerprint=digest(body),
        )
