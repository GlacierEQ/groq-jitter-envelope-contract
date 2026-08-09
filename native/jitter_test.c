#include "jitter.h"
#include "jitter.c"
#include <stdio.h>
int main(void) {
    float flat[] = {4,4.2f,3.8f,4.1f,4.0f,4,4,4,4,4};
    Envelope env = {10,5,8,2};
    EnvelopeStats st;
    if (jitter_check(flat, 10, env, &st) != JITTER_NONE || !st.ok) return 1;
    float burst[21];
    for (int i=0;i<20;i++) burst[i]=4;
    burst[20]=50;
    if (jitter_check(burst, 21, env, &st) != JITTER_BURST) return 2;
    printf("ok\n");
    return 0;
}
