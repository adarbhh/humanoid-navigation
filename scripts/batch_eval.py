"""
Batch evaluator — runs held-out and seen seeds headlessly, saves KPIs,
auto-runs a determinism check, and optionally performs a crash-safety test.

Usage
-----
  python scripts/batch_eval.py                        # held-out + determinism
  python scripts/batch_eval.py --all                  # held-out + seen + determinism + crash-safety
  python scripts/batch_eval.py --seeds 42,99,137
  python scripts/batch_eval.py --no-determinism       # skip determinism check
  python scripts/batch_eval.py --crash-safety         # run crash-safety test only

Output
------
  runs/batch_results.json          held-out KPIs
  runs/batch_results_seen.json     seen KPIs (--all only)
  runs/determinism_check.json      two-run comparison (auto unless --no-determinism)
  runs/crash_safety_check.json     SIGKILL integrity test (--all or --crash-safety)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from runner import run_episode  # noqa: E402


# ── Seed loading ──────────────────────────────────────────────────────────────

def _load_seeds(spec: str) -> list[int]:
    p = Path(spec)
    if p.exists():
        return [int(l.strip()) for l in p.read_text().splitlines() if l.strip()]
    return [int(s.strip()) for s in spec.split(",") if s.strip()]


# ── Batch run ─────────────────────────────────────────────────────────────────

def _run_batch(seeds: list[int], grid_size: int, max_time: float,
               split: str) -> list[dict]:
    print(f"\nRunning {len(seeds)} episodes  [{split}]  "
          f"grid={grid_size}x{grid_size}  max_time={max_time}s\n")

    results: list[dict] = []
    t0 = time.perf_counter()

    for i, seed in enumerate(seeds):
        print(f"\n{'-'*60}")
        print(f"[{i+1:3d}/{len(seeds)}]  seed={seed}  split={split}")
        try:
            kpis = run_episode(seed=seed, grid_size=grid_size,
                               max_time=max_time, visualize=False, record=False)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            kpis = {"seed": seed, "grid_size": grid_size,
                    "success": False, "error": str(exc)}
        kpis["split"] = split
        results.append(kpis)

        nd = i + 1
        ns = sum(r.get("success", False) for r in results)
        print(f"  running SR={ns}/{nd} ({100*ns/nd:.0f}%)")

    wall = time.perf_counter() - t0
    ns   = sum(r.get("success", False) for r in results)
    n    = len(results)
    print(f"\n{'='*60}")
    print(f"BATCH [{split}]  {n} eps  wall={wall:.1f}s ({wall/n:.1f}s/ep)")
    print(f"Success rate: {ns}/{n}  ({100*ns/n:.1f}%)")
    return results


# ── Determinism check ─────────────────────────────────────────────────────────

def _determinism_check(seed: int, grid_size: int, max_time: float) -> dict:
    """Run the same seed twice; compare structural KPIs."""
    print(f"\n{'='*60}")
    print(f"DETERMINISM CHECK  seed={seed}")
    print(f"{'='*60}")

    run_a = run_episode(seed=seed, grid_size=grid_size,
                        max_time=max_time, visualize=False, record=False)
    run_b = run_episode(seed=seed, grid_size=grid_size,
                        max_time=max_time, visualize=False, record=False)

    # Structural KPIs must be identical; ATE may differ (intentional gyro noise)
    struct_keys = ["success", "sim_time_s", "time_to_goal_s",
                   "actual_path_m", "n_wall_collisions", "n_stuck_events",
                   "failure_reason", "n_ticks"]
    noise_keys  = ["ate_rmse_m", "mean_loc_err_m", "drift_pct"]

    diffs: dict = {}
    for k in struct_keys + noise_keys:
        a, b = run_a.get(k), run_b.get(k)
        if a is None or b is None:
            diffs[k] = "N/A"
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            diffs[k] = round(abs(float(a) - float(b)), 6)
        else:
            diffs[k] = "match" if a == b else f"MISMATCH: {a!r} vs {b!r}"

    structurally_identical = all(
        diffs[k] in ("match", "N/A") or diffs[k] == 0.0
        for k in struct_keys
    )

    result = {
        "seed":   seed,
        "result": "PASS" if structurally_identical else "FAIL",
        "note":   ("Maze, path, collisions, outcome are seed-deterministic. "
                   "ATE/drift differ because gyro noise is intentionally "
                   "non-deterministic (simulates sensor imperfection)."),
        "diffs":  diffs,
        "run_a":  {k: run_a.get(k) for k in struct_keys + noise_keys},
        "run_b":  {k: run_b.get(k) for k in struct_keys + noise_keys},
    }
    print(f"\nResult: {result['result']}")
    for k, v in diffs.items():
        tag = "  [noise]" if k in noise_keys else ""
        print(f"  {k:<26}: {v}{tag}")
    return result


# ── Crash-safety test ─────────────────────────────────────────────────────────

def _crash_safety_test(seed: int, grid_size: int, kill_after_s: float = 10.0) -> dict:
    """
    Spawn a recording episode, send SIGKILL after kill_after_s seconds,
    then verify the HDF5 file is structurally valid (readable + not corrupted).
    The recorder uses periodic fsync, so the file should always be readable
    even without a clean close(); only the recording_complete flag distinguishes
    clean from truncated.
    """
    import glob
    try:
        import h5py
    except ImportError:
        return {"result": "SKIP", "reason": "h5py not installed"}

    runs_dir = ROOT / "runs"
    runs_dir.mkdir(exist_ok=True)

    cmd = [sys.executable, str(ROOT / "runner.py"),
           "--seed", str(seed), "--no-viz", "--record",
           "--max-time", "300", "--grid-size", str(grid_size)]

    print(f"\n{'='*60}")
    print(f"CRASH-SAFETY TEST  seed={seed}  kill_after={kill_after_s}s")
    print(f"{'='*60}")
    print(f"  Spawning: {' '.join(cmd[2:])}")

    proc = subprocess.Popen(
        cmd, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(kill_after_s)
    proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
    print(f"  Process killed (PID {proc.pid}) after {kill_after_s}s")

    # Give OS a moment to flush write buffers
    time.sleep(0.5)

    # Find the most recent h5 file written for this seed
    pattern = str(runs_dir / f"run_seed{seed:04d}_*.h5")
    files = sorted(glob.glob(pattern))
    if not files:
        return {"result": "FAIL", "reason": "No output file created after kill"}

    path = files[-1]
    size_kb = Path(path).stat().st_size // 1024
    print(f"  Found: {Path(path).name}  ({size_kb} KB)")

    try:
        with h5py.File(path, "r") as f:
            recording_complete = bool(f.attrs.get("recording_complete", False))
            schema_version     = str(f.attrs.get("schema_version", "unknown"))
            streams_present    = [k for k in f.keys()]
            sample_counts: dict[str, int] = {}
            for stream in streams_present:
                grp = f.get(stream)
                if grp and hasattr(grp, "items"):
                    for ds_name, ds in grp.items():
                        if hasattr(ds, "shape") and len(ds.shape) >= 1:
                            sample_counts[f"{stream}/{ds_name}"] = ds.shape[0]
                            break
            # Verify all expected top-level groups exist
            expected = {"imu", "base_state", "joint_state",
                        "lidar", "camera", "gt_pose", "meta", "path"}
            missing_groups = expected - set(streams_present)
    except Exception as exc:
        return {
            "result":   "FAIL",
            "file":     path,
            "size_kb":  size_kb,
            "reason":   f"HDF5 open failed: {exc}",
        }

    readable     = True
    clean_close  = recording_complete
    result_label = "PASS" if readable and not missing_groups else "FAIL"

    print(f"  Readable:           {readable}")
    print(f"  recording_complete: {clean_close}  "
          f"({'clean close' if clean_close else 'truncated — expected after kill'})")
    print(f"  Schema version:     {schema_version}")
    print(f"  Groups present:     {streams_present}")
    if missing_groups:
        print(f"  MISSING groups:     {missing_groups}")
    print(f"  Sample counts:      {sample_counts}")
    print(f"  Result: {result_label}")

    return {
        "result":             result_label,
        "file":               str(Path(path).name),
        "size_kb":            size_kb,
        "readable":           readable,
        "recording_complete": clean_close,
        "truncated":          not clean_close,
        "schema_version":     schema_version,
        "streams_present":    streams_present,
        "missing_groups":     list(missing_groups),
        "sample_counts":      sample_counts,
        "note": ("File is truncated but structurally valid — recorder uses "
                 "periodic fsync so HDF5 is never corrupted on SIGKILL. "
                 "recording_complete=False reliably detects incomplete runs."),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Batch KPI evaluator")
    parser.add_argument("--seeds",
                        default=str(ROOT / "seeds" / "held_out.txt"))
    parser.add_argument("--seen-seeds",
                        default=str(ROOT / "seeds" / "seen.txt"))
    parser.add_argument("--split", default="held_out",
                        choices=["held_out", "seen", "custom"])
    parser.add_argument("--grid-size",  type=int,   default=10)
    parser.add_argument("--max-time",   type=float, default=300.0)
    parser.add_argument("--out",
                        default=str(ROOT / "runs" / "batch_results.json"))
    parser.add_argument("--all", action="store_true",
                        help="Run held-out + seen + determinism + crash-safety")
    parser.add_argument("--no-determinism", action="store_true",
                        help="Skip the automatic determinism check")
    parser.add_argument("--crash-safety", action="store_true",
                        help="Run crash-safety test (spawn+kill a recording episode)")
    args = parser.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    if args.all:
        # ── Held-out batch ────────────────────────────────────────────────────
        held_seeds   = _load_seeds(args.seeds)
        held_results = _run_batch(held_seeds, args.grid_size,
                                  args.max_time, "held_out")
        held_path = ROOT / "runs" / "batch_results.json"
        held_path.write_text(json.dumps(held_results, indent=2))
        print(f"Held-out results:  {held_path}")

        # ── Seen batch ───────────────────────────────────────────────────────
        seen_file = Path(args.seen_seeds)
        if seen_file.exists():
            seen_seeds   = _load_seeds(args.seen_seeds)
            seen_results = _run_batch(seen_seeds, args.grid_size,
                                      args.max_time, "seen")
            seen_out = ROOT / "runs" / "batch_results_seen.json"
            seen_out.write_text(json.dumps(seen_results, indent=2))
            print(f"Seen results:      {seen_out}")

            held_sr = (sum(r.get("success", False) for r in held_results)
                       / len(held_results))
            seen_sr = (sum(r.get("success", False) for r in seen_results)
                       / len(seen_results))
            print(f"\nSeen SR={100*seen_sr:.1f}%  "
                  f"Held-out SR={100*held_sr:.1f}%  "
                  f"Gap={100*(seen_sr - held_sr):+.1f} pp")
        else:
            print(f"[skip seen batch — {args.seen_seeds} not found]")

        # ── Determinism check ─────────────────────────────────────────────────
        det = _determinism_check(held_seeds[0], args.grid_size, args.max_time)
        det_out = ROOT / "runs" / "determinism_check.json"
        det_out.write_text(json.dumps(det, indent=2))
        print(f"Determinism:       {det_out}")

        # ── Crash-safety test ─────────────────────────────────────────────────
        cs = _crash_safety_test(held_seeds[0], args.grid_size)
        cs_out = ROOT / "runs" / "crash_safety_check.json"
        cs_out.write_text(json.dumps(cs, indent=2))
        print(f"Crash-safety:      {cs_out}")

    else:
        # ── Single batch ──────────────────────────────────────────────────────
        seeds   = _load_seeds(args.seeds)
        results = _run_batch(seeds, args.grid_size, args.max_time, args.split)
        out_path = Path(args.out)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"Results saved: {out_path}")

        # Auto determinism check on first seed (unless suppressed)
        if not args.no_determinism and seeds:
            det = _determinism_check(seeds[0], args.grid_size, args.max_time)
            det_out = ROOT / "runs" / "determinism_check.json"
            det_out.write_text(json.dumps(det, indent=2))
            print(f"Determinism:   {det_out}")

        if args.crash_safety and seeds:
            cs = _crash_safety_test(seeds[0], args.grid_size)
            cs_out = ROOT / "runs" / "crash_safety_check.json"
            cs_out.write_text(json.dumps(cs, indent=2))
            print(f"Crash-safety:  {cs_out}")


if __name__ == "__main__":
    main()
