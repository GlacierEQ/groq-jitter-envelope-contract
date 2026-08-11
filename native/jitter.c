/* Babel: C — fixed and adaptive latency-shape envelopes. */
#include "jitter.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

static int cmp_float(const void *a, const void *b) {
    float fa = *(const float*)a, fb = *(const float*)b;
    return (fa > fb) - (fa < fb);
}

static float percentile(float *sorted, int n, float p) {
    float k = (n - 1) * p;
    int f = (int)k;
    int c = f + 1 < n ? f + 1 : f;
    if (f == c) return sorted[f];
    return sorted[f] + (sorted[c] - sorted[f]) * (k - f);
}

static float fmax2(float a, float b) { return a > b ? a : b; }

static float ewma(float previous, float value, float alpha) {
    return previous + alpha * (value - previous);
}

static float ratio(float value, float baseline) {
    return fabsf(value - baseline) / fmax2(fabsf(baseline), 0.25f);
}

static float learned_limit(float baseline, float deviation, AdaptiveEnvelopeConfig cfg) {
    return baseline + cfg.adaptive_sigma * fmax2(deviation, cfg.min_margin_ms);
}

static int valid_envelope(Envelope env) {
    return isfinite(env.max_burst_ms) && env.max_burst_ms > 0.f &&
           isfinite(env.max_median_ms) && env.max_median_ms > 0.f &&
           isfinite(env.max_p95_ms) && env.max_p95_ms > 0.f &&
           isfinite(env.max_stdev_ms) && env.max_stdev_ms > 0.f;
}

static int valid_config(AdaptiveEnvelopeConfig cfg) {
    return valid_envelope(cfg.hard_envelope) && cfg.profile_id != 0 &&
           cfg.min_windows > 0 &&
           isfinite(cfg.alpha_fast) && cfg.alpha_fast > 0.f && cfg.alpha_fast <= 1.f &&
           isfinite(cfg.alpha_slow) && cfg.alpha_slow > 0.f && cfg.alpha_slow <= cfg.alpha_fast &&
           isfinite(cfg.alpha_deviation) && cfg.alpha_deviation > 0.f && cfg.alpha_deviation <= 1.f &&
           isfinite(cfg.max_change_ratio) && cfg.max_change_ratio > 0.f &&
           isfinite(cfg.adaptive_sigma) && cfg.adaptive_sigma > 0.f &&
           isfinite(cfg.min_margin_ms) && cfg.min_margin_ms > 0.f;
}

JitterViolation jitter_check(const float *samples, int n, Envelope env, EnvelopeStats *out) {
    if (!samples || n <= 0) {
        if (out) { out->ok = 0; out->violation = JITTER_EMPTY; }
        return JITTER_EMPTY;
    }
    float *buf = (float*)malloc(sizeof(float) * (size_t)n);
    if (!buf) return JITTER_EMPTY;
    memcpy(buf, samples, sizeof(float) * (size_t)n);
    qsort(buf, (size_t)n, sizeof(float), cmp_float);
    float med = percentile(buf, n, 0.5f);
    float p95 = percentile(buf, n, 0.95f);
    float mx = buf[n - 1];
    double mean = 0;
    for (int i = 0; i < n; i++) mean += buf[i];
    mean /= n;
    double var = 0;
    for (int i = 0; i < n; i++) {
        double d = buf[i] - mean;
        var += d * d;
    }
    float sd = n > 1 ? (float)sqrt(var / n) : 0.f;
    free(buf);
    JitterViolation v = JITTER_NONE;
    if (mx > env.max_burst_ms) v = JITTER_BURST;
    else if (med > env.max_median_ms || sd > env.max_stdev_ms) v = JITTER_PLATEAU;
    else if (p95 > env.max_p95_ms) v = JITTER_TAIL;
    if (out) {
        out->median_ms = med;
        out->p95_ms = p95;
        out->max_ms = mx;
        out->stdev_ms = sd;
        out->ok = (v == JITTER_NONE);
        out->violation = v;
    }
    return v;
}

uint64_t jitter_profile_id(const char *workload_class) {
    if (!workload_class || workload_class[0] == '\0') return 0;
    uint64_t hash = UINT64_C(1469598103934665603);
    const unsigned char *p = (const unsigned char*)workload_class;
    while (*p) {
        hash ^= (uint64_t)*p++;
        hash *= UINT64_C(1099511628211);
    }
    return hash == 0 ? UINT64_C(1) : hash;
}

static void fill_adaptive(
    AdaptiveEnvelopeStats *out,
    JitterViolation violation,
    int before,
    int after,
    EnvelopeStats *fixed,
    float change_score,
    AdaptiveEnvelopeState *state,
    AdaptiveEnvelopeConfig cfg
) {
    if (!out) return;
    memset(out, 0, sizeof(*out));
    out->ok = (violation == JITTER_NONE);
    out->hard_abort = (violation != JITTER_NONE);
    out->violation = violation;
    out->windows_before = before;
    out->windows_after = after;
    out->change_score = change_score;
    if (fixed) {
        out->median_ms = fixed->median_ms;
        out->p95_ms = fixed->p95_ms;
        out->max_ms = fixed->max_ms;
        out->stdev_ms = fixed->stdev_ms;
    }
    if (state && state->initialized) {
        out->learned_median_limit_ms = learned_limit(state->slow_median, state->dev_median, cfg);
        out->learned_p95_limit_ms = learned_limit(state->slow_p95, state->dev_p95, cfg);
        out->learned_stdev_limit_ms = learned_limit(state->slow_stdev, state->dev_stdev, cfg);
    }
}

JitterViolation jitter_adaptive_check(
    const float *samples,
    int n,
    AdaptiveEnvelopeConfig cfg,
    AdaptiveEnvelopeState *state,
    AdaptiveEnvelopeStats *out
) {
    if (!state || !valid_config(cfg)) {
        fill_adaptive(out, JITTER_INVALID_SAMPLE, 0, 0, NULL, 0.f, state, cfg);
        return JITTER_INVALID_SAMPLE;
    }
    int before = state->windows;
    if (!samples || n <= 0) {
        fill_adaptive(out, JITTER_EMPTY, before, before, NULL, 0.f, state, cfg);
        return JITTER_EMPTY;
    }
    for (int i = 0; i < n; i++) {
        if (!isfinite(samples[i]) || samples[i] < 0.f) {
            fill_adaptive(out, JITTER_INVALID_SAMPLE, before, before, NULL, 0.f, state, cfg);
            return JITTER_INVALID_SAMPLE;
        }
    }
    if (state->initialized && state->profile_id != cfg.profile_id) {
        fill_adaptive(out, JITTER_PROFILE_MISMATCH, before, before, NULL, 0.f, state, cfg);
        return JITTER_PROFILE_MISMATCH;
    }

    EnvelopeStats fixed;
    memset(&fixed, 0, sizeof(fixed));
    JitterViolation hard = jitter_check(samples, n, cfg.hard_envelope, &fixed);
    if (hard != JITTER_NONE) {
        fill_adaptive(out, hard, before, before, &fixed, 0.f, state, cfg);
        return hard;
    }

    if (!state->initialized) {
        memset(state, 0, sizeof(*state));
        state->initialized = 1;
        state->profile_id = cfg.profile_id;
        state->windows = 1;
        state->fast_median = state->slow_median = fixed.median_ms;
        state->fast_p95 = state->slow_p95 = fixed.p95_ms;
        state->fast_stdev = state->slow_stdev = fixed.stdev_ms;
        fill_adaptive(out, JITTER_NONE, before, state->windows, &fixed, 0.f, state, cfg);
        return JITTER_NONE;
    }

    float next_fast_median = ewma(state->fast_median, fixed.median_ms, cfg.alpha_fast);
    float next_fast_p95 = ewma(state->fast_p95, fixed.p95_ms, cfg.alpha_fast);
    float next_fast_stdev = ewma(state->fast_stdev, fixed.stdev_ms, cfg.alpha_fast);
    float change_score = fmax2(
        ratio(next_fast_median, state->slow_median),
        fmax2(ratio(next_fast_p95, state->slow_p95), ratio(next_fast_stdev, state->slow_stdev))
    );
    int warmed = state->windows >= cfg.min_windows;
    float median_limit = learned_limit(state->slow_median, state->dev_median, cfg);
    float p95_limit = learned_limit(state->slow_p95, state->dev_p95, cfg);
    float stdev_limit = learned_limit(state->slow_stdev, state->dev_stdev, cfg);

    if (warmed && change_score > cfg.max_change_ratio) {
        fill_adaptive(out, JITTER_CHANGE_POINT, before, before, &fixed, change_score, state, cfg);
        return JITTER_CHANGE_POINT;
    }
    if (warmed && (
        fixed.median_ms > median_limit ||
        fixed.p95_ms > p95_limit ||
        fixed.stdev_ms > stdev_limit
    )) {
        fill_adaptive(out, JITTER_ADAPTIVE_PROFILE, before, before, &fixed, change_score, state, cfg);
        return JITTER_ADAPTIVE_PROFILE;
    }

    float old_slow_median = state->slow_median;
    float old_slow_p95 = state->slow_p95;
    float old_slow_stdev = state->slow_stdev;
    state->fast_median = next_fast_median;
    state->fast_p95 = next_fast_p95;
    state->fast_stdev = next_fast_stdev;
    state->slow_median = ewma(state->slow_median, fixed.median_ms, cfg.alpha_slow);
    state->slow_p95 = ewma(state->slow_p95, fixed.p95_ms, cfg.alpha_slow);
    state->slow_stdev = ewma(state->slow_stdev, fixed.stdev_ms, cfg.alpha_slow);
    state->dev_median = ewma(state->dev_median, fabsf(fixed.median_ms - old_slow_median), cfg.alpha_deviation);
    state->dev_p95 = ewma(state->dev_p95, fabsf(fixed.p95_ms - old_slow_p95), cfg.alpha_deviation);
    state->dev_stdev = ewma(state->dev_stdev, fabsf(fixed.stdev_ms - old_slow_stdev), cfg.alpha_deviation);
    state->windows++;
    fill_adaptive(out, JITTER_NONE, before, state->windows, &fixed, change_score, state, cfg);
    return JITTER_NONE;
}
