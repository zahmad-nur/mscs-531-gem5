#!/usr/bin/env bash
#
# run_sweep.sh
#
# Runs the full FloatSimdFU (opLat, issueLat) x thread-count design
# space for the daxpy_mt TLP experiment (Part 2, Tasks 2-3).
#
# Env vars (override as needed):
#   GEM5_BIN   path to gem5.opt              (default: ./build/X86/gem5.opt)
#   CONFIG     path to config_daxpy_tlp.py    (default: ./config_daxpy_tlp.py)
#   DAXPY_BIN  path to compiled daxpy_mt      (default: ./daxpy_mt)
#   DAXPY_N    vector length n                (default: 1000000)
#   OUT_ROOT   where per-run m5out dirs go    (default: ./results)
#
# Usage:
#   chmod +x run_sweep.sh
#   ./run_sweep.sh
#
# This will take a while -- 6 FU configs x 4 thread counts = 24 gem5
# runs. Comment out combos/thread_counts entries below to do a partial
# sweep first and sanity-check output before committing to the full run.

set -euo pipefail

GEM5_BIN=${GEM5_BIN:-./build/X86/gem5.opt}
CONFIG=${CONFIG:-./config_daxpy_tlp.py}
DAXPY_BIN=${DAXPY_BIN:-./daxpy_mt}
N=${DAXPY_N:-1000000}
OUT_ROOT=${OUT_ROOT:-./results}

if [[ ! -x "$GEM5_BIN" ]]; then
  echo "ERROR: gem5 binary not found/executable at $GEM5_BIN" >&2
  echo "  set GEM5_BIN=/path/to/gem5.opt or run from your gem5 checkout root" >&2
  exit 1
fi
if [[ ! -x "$DAXPY_BIN" ]]; then
  echo "ERROR: daxpy binary not found/executable at $DAXPY_BIN" >&2
  echo "  build it first, e.g.:" >&2
  echo "  x86_64-linux-gnu-gcc -O2 -static -pthread -o daxpy_mt daxpy_mt.c" >&2
  exit 1
fi

mkdir -p "$OUT_ROOT"

# (opLat issueLat) pairs summing to 7 cycles, per the assignment
combos=(
  "1 6"
  "2 5"
  "3 4"
  "4 3"
  "5 2"
  "6 1"
)

# includes 1 as the single-threaded baseline for speedup calculations
thread_counts=(1 2 4 8)

total=$(( ${#combos[@]} * ${#thread_counts[@]} ))
count=0

for combo in "${combos[@]}"; do
  read -r OP ISSUE <<< "$combo"
  for T in "${thread_counts[@]}"; do
    count=$((count + 1))
    OUTDIR="$OUT_ROOT/op${OP}_issue${ISSUE}_t${T}"
    echo "[$count/$total] opLat=$OP issueLat=$ISSUE threads=$T -> $OUTDIR"

    "$GEM5_BIN" --outdir="$OUTDIR" "$CONFIG" \
      --cmd="$DAXPY_BIN" \
      --options="$T $N" \
      --num-cpus="$T" \
      --op-lat="$OP" \
      --issue-lat="$ISSUE" \
      > "$OUTDIR.log" 2>&1 || echo "  !! run failed, see $OUTDIR.log"
  done
done

echo ""
echo "Sweep complete. Per-run stats in $OUT_ROOT/*/stats.txt"
echo "Next: python3 parse_stats.py $OUT_ROOT --out results.csv"