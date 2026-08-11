#include "jitter.h"
#include "jitter.c"
#include <math.h>
#include <stdio.h>
#include <string.h>

static AdaptiveEnvelopeConfig profile(const char *name) {
    AdaptiveEnvelopeConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.hard_envelope = (Envelope){20.f, 15.f, 18.f, 6.f};
    cfg.profile_id = jitter_profile_id(name);
    cfg.min_windows = 4;
    cfg.alpha_fast = 0.50f;
    cfg.alpha_slow = 0.10f;
    cfg.alpha_deviation = 0.25f;
    cfg.max_change_ratio = 0.30f;
    cfg.adaptive_sigma = 4.f;
    cfg.min_margin_ms = 0.25f;
    return cfg;
}

static int warm(AdaptiveEnvelopeConfig cfg, AdaptiveEnvelopeState *state) {
    float stable[20];
    for (int i = 0; i < 20; i++) stable[i] = 4.f;
    AdaptiveEnvelopeStats out;
    for (int window = 0; window < 4; window++) {
        if (jitter_adaptive_check(stable, 20, cfg, state, &out) != JITTER_NONE) return 0;
        if (!out.ok || out.hard_abort) return 0;
    }
    return state->windows == 4;
}

int main(void) {
    /* Legacy API remains unchanged. */
    float flat[] = {4,4.2f,3.8f,4.1f,4.0f,4,4,4,4,4};
    Envelope env = {10,5,8,2};
    EnvelopeStats st;
    if (jitter_check(flat, 10, env, &st) != JITTER_NONE || !st.ok) return 1;
    float burst[21];
    for (int i=0;i<20;i++) burst[i]=4;
    burst[20]=50;
    if (jitter_check(burst, 21, env, &st) != JITTER_BURST) return 2;

    /* Adaptive profile warms on passing windows. */
    AdaptiveEnvelopeConfig cfg = profile("interactive");
    AdaptiveEnvelopeState state;
    memset(&state, 0, sizeof(state));
    if (!warm(cfg, &state)) return 3;

    /* A new latency regime hard-aborts and cannot teach itself into normality. */
    float jump[20];
    for (int i = 0; i < 20; i++) jump[i] = 8.f;
    AdaptiveEnvelopeStats change;
    if (jitter_adaptive_check(jump, 20, cfg, &state, &change) != JITTER_CHANGE_POINT) return 4;
    if (!change.hard_abort || change.windows_before != 4 || change.windows_after != 4) return 5;
    if (change.change_score <= cfg.max_change_ratio || state.windows != 4) return 6;
    if (jitter_adaptive_check(jump, 20, cfg, &state, &change) != JITTER_CHANGE_POINT) return 7;
    if (state.windows != 4) return 8;

    /* Caller-owned state is cryptographically-stable-ID scoped to one class. */
    AdaptiveEnvelopeConfig bulk_cfg = cfg;
    bulk_cfg.profile_id = jitter_profile_id("bulk");
    if (jitter_adaptive_check(flat, 10, bulk_cfg, &state, &change) != JITTER_PROFILE_MISMATCH) return 9;
    if (state.windows != 4) return 10;

    /* Fixed hard limits always dominate learned state. */
    float hard_burst[20];
    for (int i = 0; i < 19; i++) hard_burst[i] = 4.f;
    hard_burst[19] = 50.f;
    if (jitter_adaptive_check(hard_burst, 20, cfg, &state, &change) != JITTER_BURST) return 11;
    if (state.windows != 4) return 12;

    /* Learned envelope can hard-abort even when change-point threshold is loose. */
    AdaptiveEnvelopeConfig profile_cfg = profile("profile-breach");
    profile_cfg.max_change_ratio = 10.f;
    profile_cfg.adaptive_sigma = 1.f;
    profile_cfg.min_margin_ms = 0.10f;
    AdaptiveEnvelopeState profile_state;
    memset(&profile_state, 0, sizeof(profile_state));
    if (!warm(profile_cfg, &profile_state)) return 13;
    float elevated[20];
    for (int i = 0; i < 20; i++) elevated[i] = 5.f;
    if (jitter_adaptive_check(elevated, 20, profile_cfg, &profile_state, &change) != JITTER_ADAPTIVE_PROFILE) return 14;
    if (profile_state.windows != 4) return 15;

    /* Invalid evidence fails closed and does not mutate the baseline. */
    float invalid[] = {4.f, NAN};
    if (jitter_adaptive_check(invalid, 2, cfg, &state, &change) != JITTER_INVALID_SAMPLE) return 16;
    if (state.windows != 4) return 17;
    if (jitter_profile_id("") != 0 || jitter_profile_id(NULL) != 0) return 18;

    printf("ok\n");
    return 0;
}
