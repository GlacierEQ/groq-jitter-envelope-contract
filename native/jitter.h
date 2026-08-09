#ifndef JITTER_H
#define JITTER_H
typedef enum { JITTER_NONE=0, JITTER_BURST, JITTER_PLATEAU, JITTER_TAIL, JITTER_EMPTY } JitterViolation;
typedef struct { float max_burst_ms, max_median_ms, max_p95_ms, max_stdev_ms; } Envelope;
typedef struct {
    int ok; JitterViolation violation;
    float median_ms, p95_ms, max_ms, stdev_ms;
} EnvelopeStats;
JitterViolation jitter_check(const float *samples, int n, Envelope env, EnvelopeStats *out);
#endif
