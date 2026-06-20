"""
Compare A* vs Dijkstra path planners on the same seed.

Usage:
    conda run -n robotics-assignment python scripts/compare_planners.py --seed 42
    conda run -n robotics-assignment python scripts/compare_planners.py --seed 42 --no-viz
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from runner import run_episode

METRICS = [
    ("plan_time_ms",         "Planning time (ms)",         ".2f"),
    ("planned_path_m",       "Planned path length (m)",    ".2f"),
    ("optimal_path_m",       "Optimal path (m)",           ".2f"),
    ("time_to_goal_s",       "Time to goal (s)",           ".1f"),
    ("actual_path_m",        "Actual path traveled (m)",   ".2f"),
    ("path_efficiency",      "Path efficiency",            ".4f"),
    ("n_wall_collisions",    "Wall collisions",            "d"),
    ("n_stuck_events",       "Stuck events",               "d"),
    ("mean_loc_err_m",       "Mean loc error (m)",         ".3f"),
    ("ate_rmse_m",           "ATE RMSE (m)",               ".3f"),
    ("mtbf_m",               "MTBF (m)",                   ".2f"),
    ("success",              "Success",                    ""),
]


def _fmt(val, fmt: str) -> str:
    if val is None:
        return "N/A"
    if fmt == "":
        return str(val)
    if fmt == "d":
        return str(int(val))
    return format(float(val), fmt)


def _diff(a, b, fmt: str) -> str:
    if a is None or b is None or fmt == "" or fmt == "d" and isinstance(a, bool):
        return "—"
    try:
        fa, fb = float(a), float(b)
        d = fb - fa
        pct = (d / fa * 100) if fa != 0 else 0.0
        sign = "+" if d >= 0 else ""
        if fmt == "d":
            return f"{sign}{int(d):d}  ({sign}{pct:.1f}%)"
        return f"{sign}{d:{fmt}}  ({sign}{pct:.1f}%)"
    except Exception:
        return "—"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed",      type=int,   default=42)
    parser.add_argument("--grid-size", type=int,   default=10)
    parser.add_argument("--max-time",  type=float, default=300.0)
    parser.add_argument("--no-viz",    action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Planner comparison  seed={args.seed}  grid={args.grid_size}x{args.grid_size}")
    print("=" * 60)

    PLANNERS = [
        ("dijkstra", "Dijkstra"),
        ("astar",    "A* (w=1)"),
        ("wastar3",  "Weighted A* w=3"),
        ("wastar10", "Weighted A* w=10"),
    ]

    kpis = {}
    for key, label in PLANNERS:
        print(f"\n--- Running {label} ---")
        kpis[key] = run_episode(
            seed=args.seed, grid_size=args.grid_size,
            max_time=args.max_time, visualize=not args.no_viz,
            planner=key, planner_center_weight=0.0,
        )

    # ── Print comparison table ────────────────────────────────────────────────
    col_w = [28] + [18] * len(PLANNERS)
    sep = "+" + "+".join("-" * w for w in col_w) + "+"

    def rowp(*cells):
        parts = [f" {str(c):<{col_w[i]-2}} " for i, c in enumerate(cells)]
        print("|" + "|".join(parts) + "|")

    print("\n")
    print(sep)
    rowp("Metric", *[lbl for _, lbl in PLANNERS])
    print(sep)
    for key, label, fmt in METRICS:
        vals = [kpis[pk].get(key) for pk, _ in PLANNERS]
        rowp(label, *[_fmt(v, fmt) for v in vals])
    print(sep)
    print()

    # ── Save JSON ─────────────────────────────────────────────────────────────
    out = {
        "meta": {"seed": args.seed, "grid_size": args.grid_size},
    }
    for pk, lbl in PLANNERS:
        out[pk] = {k: kpis[pk].get(k) for k, _, _ in METRICS}

    out_path = ROOT / "runs" / "planner_comparison.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
