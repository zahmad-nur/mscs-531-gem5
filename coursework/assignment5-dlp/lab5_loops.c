#include <stdio.h>
#include <stdlib.h>

#define N 1000000

// Baseline: simple loop, one iteration at a time
void sum_baseline(int n, float *a, float *result) {
    float sum = 0.0f;
    for (int i = 0; i < n; i++) {
        sum += a[i];
    }
    *result = sum;
}

// Unrolled: process 4 elements per loop iteration
void sum_unrolled(int n, float *a, float *result) {
    float sum = 0.0f;
    int i;
    for (i = 0; i + 3 < n; i += 4) {
        sum += a[i] + a[i+1] + a[i+2] + a[i+3];
    }
    for (; i < n; i++) {
        sum += a[i];
    }
    *result = sum;
}

int main() {
    float *a = malloc(N * sizeof(float));
    for (int i = 0; i < N; i++) a[i] = 1.0f;

    float result;
#ifdef UNROLLED
    sum_unrolled(N, a, &result);
#else
    sum_baseline(N, a, &result);
#endif

    printf("Sum = %f\n", result);
    free(a);
    return 0;
}
