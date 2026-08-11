#ifndef JITTER_H
#define JITTER_H
#include <stdint.h>

typedef enum {
    JITTER_NONE=0,
    JITTER_BURST,
    JITTER_PLATEAU,
    JITTER_TAIL,
    JITTER_EMPTY,
    JITTER_INVALID_SAMPLE,
    JITTER_PROFILE_MISMATCH,
    JITTER_CHANGE_POINT,
    JITTER_ADAPTIVE_PROFILE
} JitterViolation;

typedef struct {
    float max_burst_ms, max_median_ms, max_p95_ms, max_stdev_ms;
} Envelope;

typedef struct {
    int ok;
    JitterViolation violation;
    float median_ms, p95_ms, max_ms, stdev_ms;
} EnvelopeStats;

typedef struct {
    Envelope hard_envelope;
    uint64_t profile_id;
    int min_windows;
    float alpha_fast;
    float alpha_slow;
    float alpha_deviation;
    float max_change_ratio;
    float adaptive_sigma;
    float min_margin_ms;
} AdaptiveEnvelopeConfig;

typedef struct {
    int initialized;
    uint64_t profile_id;
    int windows;
    float fast_median, slow_median, dev_median;
    float fast_p95, slow_p95, dev_p95;
    float fast_stdev, slow_stdev, dev_stdev;
} AdaptiveEnvelopeState;

typedef struct {
    int ok;
    int hard_abort;
    JitterViolation violation;
    int windows_before;
    int windows_after;
    float median_ms, p95_ms, max_ms, stdev_ms;
    float change_score;
    float learned_median_limit_ms;
    float learned_p95_limit_ms;
    float learned_stdev_limit_ms;
} AdaptiveEnvelopeStats;

JitterViolation jitter_check(const float *samples, int n, Envelope env, EnvelopeStats *out);
uint64_t jitter_profile_id(const char *workload_class);
JitterViolation jitter_adaptive_check(
    const float *samples,
    int n,
    AdaptiveEnvelopeConfig cfg,
    AdaptiveEnvelopeState *state,
    AdaptiveEnvelopeStats *out
);
#endif
