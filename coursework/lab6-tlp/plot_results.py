#!/usr/bin/env python3
"""
plot_results.py

Reads results.csv (from parse_stats.py) and produces the graphs Part 2
Task 5 asks for:

  1. speedup_vs_threads.png  -- parallel speedup vs thread count,
     one line per (opLat, issueLat) FU config
  2. ipc_vs_fu_config.png    -- avg per-core IPC vs FU config,
     one line per thread count
  3. sim_time_vs_fu_config.png -- sim_seconds vs FU config,
     one line per thread count

Usage:
  python3 plot_results.py results.csv --outdir plots/
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_rows(path):
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            for k in ("opLat", "issueLat", "threads"):
                r[k] = int(r[k]) if r[k] not in (None, "") else None
            for k in ("sim_seconds", "avg_core_ipc"):
                r[k] = float(r[k]) if r.get(k) not in (None, "") else None
            rows.append(r)
    return rows


def fu_label(op_lat, issue_lat):
    return f"opLat={op_lat},issueLat={issue_lat}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--outdir", default="plots")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(args.csv_path)

    # group by (opLat, issueLat) -> {threads: sim_seconds}
    by_config = defaultdict(dict)
    for r in rows:
        if r["sim_seconds"] is None:
            continue
        key = (r["opLat"], r["issueLat"])
        by_config[key][r["threads"]] = r["sim_seconds"]

    # ---- 1. speedup vs threads ----
    plt.figure(figsize=(7, 5))
    for (op_lat, issue_lat), tdict in sorted(by_config.items()):
        if 1 not in tdict:
            print(f"skip {fu_label(op_lat, issue_lat)}: no single-thread baseline (t=1) found")
            continue
        baseline = tdict[1]
        threads_sorted = sorted(tdict.keys())
        speedups = [baseline / tdict[t] for t in threads_sorted]
        plt.plot(threads_sorted, speedups, marker="o", label=fu_label(op_lat, issue_lat))
    plt.plot([1, 8], [1, 8], linestyle="--", color="gray", linewidth=1, label="ideal linear speedup")
    plt.xlabel("Thread count")
    plt.ylabel("Parallel speedup (vs. 1 thread, same FU config)")
    plt.title("Daxpy parallel speedup vs. FloatSimdFU design")
    plt.legend(fontsize=8)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outdir / "speedup_vs_threads.png", dpi=150)
    plt.close()

    # ---- 2. IPC vs FU config, one line per thread count ----
    by_threads = defaultdict(dict)
    for r in rows:
        if r["avg_core_ipc"] is None:
            continue
        by_threads[r["threads"]][(r["opLat"], r["issueLat"])] = r["avg_core_ipc"]

    plt.figure(figsize=(7, 5))
    for t, cfgdict in sorted(by_threads.items()):
        configs_sorted = sorted(cfgdict.keys())
        labels = [fu_label(*c) for c in configs_sorted]
        ipcs = [cfgdict[c] for c in configs_sorted]
        plt.plot(labels, ipcs, marker="o", label=f"{t} thread(s)")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.ylabel("Average per-core IPC")
    plt.title("IPC vs. FloatSimdFU design, by thread count")
    plt.legend(fontsize=8)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outdir / "ipc_vs_fu_config.png", dpi=150)
    plt.close()

    # ---- 3. sim_seconds vs FU config, one line per thread count ----
    plt.figure(figsize=(7, 5))
    for t, tdict in sorted(by_threads.items()):
        pass  # placeholder to keep structure parallel; real data pulled below

    by_threads_time = defaultdict(dict)
    for r in rows:
        if r["sim_seconds"] is None:
            continue
        by_threads_time[r["threads"]][(r["opLat"], r["issueLat"])] = r["sim_seconds"]

    for t, cfgdict in sorted(by_threads_time.items()):
        configs_sorted = sorted(cfgdict.keys())
        labels = [fu_label(*c) for c in configs_sorted]
        times = [cfgdict[c] for c in configs_sorted]
        plt.plot(labels, times, marker="o", label=f"{t} thread(s)")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.ylabel("Simulated time (sim_seconds)")
    plt.title("Simulation time vs. FloatSimdFU design, by thread count")
    plt.legend(fontsize=8)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outdir / "sim_time_vs_fu_config.png", dpi=150)
    plt.close()

    print(f"Wrote plots to {outdir}/")


if __name__ == "__main__":
    main()