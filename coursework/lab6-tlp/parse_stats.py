#!/usr/bin/env python3
"""
parse_stats.py

Walks a directory of gem5 m5out-style run directories (as produced by
run_sweep.sh, named op<OP>_issue<ISSUE>_t<THREADS>/) and extracts the
metrics Part 2 Task 4 asks for into a single results.csv:

  - overall simulation time (sim_seconds)
  - per-core IPC and CPI
  - FloatSimdFU utilization (busy-cycle stats, name varies by gem5
    version -- see NOTE below)
  - instruction/cycle counts needed to sanity-check the above

Usage:
  python3 parse_stats.py results/ --out results.csv

Then compute speedup and plot with plot_results.py.

NOTE on FU utilization: gem5 does NOT tag stats by functional-unit
name. It tags them by instruction opClass (e.g. "FloatAdd",
"SimdFloatMult", "SimdFloatCvt"), broken out under
system.cpu<N>.commitStats0.committedInstType::<opClass>. The set of
opClasses below is copied directly from MinorDefaultFloatSimdFU's
opClasses list in src/cpu/minor/BaseMinorCPU.py -- this is what
"FloatSimdFU utilization" actually means: the sum of committed
instructions across every opClass that FU is responsible for.
FloatMemRead/FloatMemWrite are deliberately excluded even though they
sound related -- per BaseMinorCPU.py those two belong to
MinorDefaultMemFU, not the FloatSimd unit.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

DIR_NAME_RE = re.compile(r"op(?P<oplat>\d+)_issue(?P<issuelat>\d+)_t(?P<threads>\d+)$")
STAT_LINE_RE = re.compile(r"^(\S+)\s+(\S+)")
CPU_STAT_RE = re.compile(r"^system\.cpu(\d+)\.(\w+)$")
COMMIT_TYPE_RE = re.compile(r"^system\.cpu(\d+)\.commitStats0\.committedInstType::(\w+)$")

FLOATSIMD_OPCLASSES = {
    "FloatAdd", "FloatCmp", "FloatCvt", "FloatMisc", "FloatMult",
    "FloatMultAcc", "FloatDiv", "FloatSqrt", "Bf16Cvt", "SimdAdd",
    "SimdAddAcc", "SimdAlu", "SimdCmp", "SimdCvt", "SimdMisc", "SimdMult",
    "SimdMultAcc", "SimdMatMultAcc", "SimdShift", "SimdShiftAcc", "SimdDiv",
    "SimdSqrt", "SimdFloatAdd", "SimdFloatAlu", "SimdFloatCmp",
    "SimdFloatCvt", "SimdFloatDiv", "SimdFloatMisc", "SimdFloatMult",
    "SimdFloatMultAcc", "SimdFloatMatMultAcc", "SimdFloatSqrt",
    "SimdReduceAdd", "SimdReduceAlu", "SimdReduceCmp", "SimdFloatReduceAdd",
    "SimdFloatReduceCmp", "SimdAes", "SimdAesMix", "SimdSha1Hash",
    "SimdSha1Hash2", "SimdSha256Hash", "SimdSha256Hash2", "SimdShaSigma2",
    "SimdShaSigma3", "SimdSha3", "SimdSm4e", "SimdCrc", "Matrix",
    "MatrixMov", "MatrixOP", "SimdExt", "SimdFloatExt", "SimdConfig",
    "SimdDotProd", "SimdBf16Add", "SimdBf16Cmp", "SimdBf16Cvt",
    "SimdBf16DotProd", "SimdBf16MatMultAcc", "SimdBf16Mult",
    "SimdBf16MultAcc",
}


def parse_stats_file(path):
    """Return dict of {stat_name: value_str} for every scalar stat line."""
    stats = {}
    if not path.exists():
        return stats
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("---"):
                continue
            m = STAT_LINE_RE.match(line)
            if m:
                stats[m.group(1)] = m.group(2)
    return stats


def to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir", help="root dir containing op*_issue*_t*/ subdirs")
    ap.add_argument("--out", default="results.csv")
    args = ap.parse_args()

    root = Path(args.results_dir)
    run_dirs = sorted(d for d in root.iterdir() if d.is_dir() and DIR_NAME_RE.match(d.name))

    if not run_dirs:
        print(f"No run directories matching op<N>_issue<N>_t<N> found under {root}", file=sys.stderr)
        sys.exit(1)

    rows = []

    for d in run_dirs:
        m = DIR_NAME_RE.match(d.name)
        op_lat = int(m.group("oplat"))
        issue_lat = int(m.group("issuelat"))
        threads = int(m.group("threads"))

        stats = parse_stats_file(d / "stats.txt")
        if not stats:
            print(f"WARNING: no stats.txt (or empty) in {d} -- run may have failed", file=sys.stderr)
            continue

        # NOTE: top-level summary stats are camelCase in this gem5
        # version (simSeconds/simTicks/finalTick), not the snake_case
        # (sim_seconds/etc.) used in some older gem5 docs/examples --
        # confirmed against real stats.txt output.
        row = {
            "opLat": op_lat,
            "issueLat": issue_lat,
            "threads": threads,
            "sim_seconds": to_float(stats.get("simSeconds")),
            "sim_ticks": to_float(stats.get("simTicks")),
            "final_tick": to_float(stats.get("finalTick")),
        }

        # per-core IPC / CPI / cycle counts -- these are direct,
        # single-level stats (system.cpu<N>.ipc etc.), confirmed
        # against real stats.txt output.
        per_core = {}
        for key, val in stats.items():
            cm = CPU_STAT_RE.match(key)
            if not cm:
                continue
            core_id, field = cm.group(1), cm.group(2)
            per_core.setdefault(core_id, {})[field] = val

        ipcs = []
        for core_id, fields in sorted(per_core.items()):
            ipc = to_float(fields.get("ipc"))
            cpi = to_float(fields.get("cpi"))
            row[f"cpu{core_id}_ipc"] = ipc
            row[f"cpu{core_id}_cpi"] = cpi
            row[f"cpu{core_id}_numCycles"] = to_float(fields.get("numCycles"))
            if ipc is not None:
                ipcs.append(ipc)
        row["avg_core_ipc"] = sum(ipcs) / len(ipcs) if ipcs else None

        # committed instruction count is nested under commitStats0, so
        # it needs its own regex rather than the flat CPU_STAT_RE above
        for key, val in stats.items():
            cm = re.match(r"^system\.cpu(\d+)\.commitStats0\.numInsts$", key)
            if cm:
                row[f"cpu{cm.group(1)}_committedInsts"] = to_float(val)

        # FloatSimdFU utilization: sum committed instructions across
        # every opClass that MinorDefaultFloatSimdFU actually handles
        # (see FLOATSIMD_OPCLASSES above), per core, plus that core's
        # total committed instructions so you can also report it as a
        # percentage.
        floatsimd_sums = {}
        total_committed = {}
        for key, val in stats.items():
            cm = COMMIT_TYPE_RE.match(key)
            if not cm:
                continue
            core_id, op_class = cm.group(1), cm.group(2)
            v = to_float(val)
            if v is None:
                continue
            if op_class == "total":
                total_committed[core_id] = v
            elif op_class in FLOATSIMD_OPCLASSES:
                floatsimd_sums[core_id] = floatsimd_sums.get(core_id, 0) + v

        for core_id in sorted(set(floatsimd_sums) | set(total_committed)):
            fs = floatsimd_sums.get(core_id, 0)
            tot = total_committed.get(core_id)
            row[f"cpu{core_id}_floatsimd_insts"] = fs
            row[f"cpu{core_id}_floatsimd_pct"] = (100.0 * fs / tot) if tot else None

        rows.append(row)

    # union of all columns across rows (a run that never executed any
    # float/SIMD ops -- e.g. a config bug -- would still produce 0s,
    # not missing columns, so this union is mostly a safety net)
    base_cols = ["opLat", "issueLat", "threads", "sim_seconds", "sim_ticks",
                 "final_tick", "avg_core_ipc"]
    per_core_cols = sorted({k for r in rows for k in r if k.startswith("cpu")})
    fieldnames = base_cols + per_core_cols

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()