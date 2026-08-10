/*
 * daxpy_mt.c
 *
 * Multi-threaded DAXPY kernel: y[i] = a*x[i] + y[i]
 *
 * Each pthread is pinned (by gem5's SE-mode thread scheduler, not by us)
 * to its own CPU context, so running this with --num-cpus=T in the gem5
 * config and launching T threads gives one thread per simulated core --
 * this is the multi-core TLP setup Part 2 asks for.
 *
 * Usage:
 *   ./daxpy_mt <num_threads> <n>
 *
 * Build (plain, no gem5 stats markers):
 *   x86_64-linux-gnu-gcc -O2 -static -pthread -o daxpy_mt daxpy_mt.c
 *
 * Build (with gem5 m5ops region-of-interest markers -- recommended once
 * you have the m5 utility built, see README.md "m5ops" section):
 *   x86_64-linux-gnu-gcc -O2 -static -pthread -DUSE_M5OPS \
 *     -I<gem5>/include -o daxpy_mt daxpy_mt.c <gem5>/util/m5/build/x86/out/libm5.a
 *
 * Static linking matters: gem5 SE mode has no dynamic linker/loader
 * support by default, so a dynamically-linked binary will fail to run.
 */

#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>

#ifdef USE_M5OPS
#include <gem5/m5ops.h>
#define ROI_BEGIN() m5_reset_stats(0, 0)
#define ROI_END()   m5_dump_stats(0, 0)
#else
#define ROI_BEGIN() ((void)0)
#define ROI_END()   ((void)0)
#endif

typedef struct {
    double a;
    double *x;
    double *y;
    long start;   /* inclusive */
    long end;     /* exclusive */
} thread_arg_t;

/* ---- the actual daxpy work: this is the region TLP is being measured
 * across. keep it simple -- no locks, no shared writes -- so any
 * slowdown you see comes from the FloatSimd FU / core contention, not
 * from synchronization artifacts. */
static void *daxpy_worker(void *argp) {
    thread_arg_t *arg = (thread_arg_t *)argp;
    for (long i = arg->start; i < arg->end; i++) {
        arg->y[i] = arg->a * arg->x[i] + arg->y[i];
    }
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: %s <num_threads> <n>\n", argv[0]);
        return 1;
    }

    long num_threads = strtol(argv[1], NULL, 10);
    long n = strtol(argv[2], NULL, 10);

    if (num_threads < 1 || n < num_threads) {
        fprintf(stderr, "num_threads must be >=1 and <= n\n");
        return 1;
    }

    double a = 2.5;
    double *x = malloc(n * sizeof(double));
    double *y = malloc(n * sizeof(double));
    if (!x || !y) {
        fprintf(stderr, "allocation failed\n");
        return 1;
    }

    /* deterministic init -- no file I/O, no rand() syscalls, keeps SE
     * mode setup simple and keeps runs reproducible across configs */
    for (long i = 0; i < n; i++) {
        x[i] = (double)(i % 97) * 0.5;
        y[i] = (double)(i % 31) * 0.25;
    }

    pthread_t *threads = malloc(num_threads * sizeof(pthread_t));
    thread_arg_t *args = malloc(num_threads * sizeof(thread_arg_t));

    long chunk = n / num_threads;
    for (long t = 0; t < num_threads; t++) {
        args[t].a = a;
        args[t].x = x;
        args[t].y = y;
        args[t].start = t * chunk;
        args[t].end = (t == num_threads - 1) ? n : (t + 1) * chunk;
    }

    /* ---- ROI: everything gem5's stats should reflect for the TLP
     * comparison is inside this region. Setup (malloc/init above) and
     * teardown (verification below) are excluded so opLat/issueLat
     * effects on the FloatSimdFU aren't diluted by scalar setup code. */
    ROI_BEGIN();

    for (long t = 0; t < num_threads; t++) {
        pthread_create(&threads[t], NULL, daxpy_worker, &args[t]);
    }
    for (long t = 0; t < num_threads; t++) {
        pthread_join(threads[t], NULL);
    }

    ROI_END();
    /* ---- end ROI ---- */

    /* cheap checksum so the compiler can't optimize the loop away and
     * so you have a sanity check that output is identical across all
     * FU configs (it should be -- opLat/issueLat only change timing,
     * never numerical results) */
    double checksum = 0.0;
    for (long i = 0; i < n; i++) checksum += y[i];
    printf("threads=%ld n=%ld checksum=%f\n", num_threads, n, checksum);

    free(x);
    free(y);
    free(threads);
    free(args);
    return 0;
}