/* Babel: C — latency shape envelope (median/p95/max/stdev). */
#include "jitter.h"
#include <stdlib.h>
#include <math.h>
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
    for (int i = 0; i < n; i++) { double d = buf[i] - mean; var += d * d; }
    float sd = n > 1 ? (float)sqrt(var / n) : 0.f;
    free(buf);
    JitterViolation v = JITTER_NONE;
    if (mx > env.max_burst_ms) v = JITTER_BURST;
    else if (med > env.max_median_ms || sd > env.max_stdev_ms) v = JITTER_PLATEAU;
    else if (p95 > env.max_p95_ms) v = JITTER_TAIL;
    if (out) {
        out->median_ms = med; out->p95_ms = p95; out->max_ms = mx; out->stdev_ms = sd;
        out->ok = (v == JITTER_NONE); out->violation = v;
    }
    return v;
}
