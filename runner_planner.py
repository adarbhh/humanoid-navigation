"""
runner_planner.py — run an episode using a specific path planning algorithm.

The robot actually navigates the planner's own path (not the maze solution),
so different planners produce visibly different routes in the MuJoCo viewer.

Planner waypoints are snapped to the nearest maze corridor centre so the
pure-pursuit controller can track them reliably.

Usage:
    conda run -n robotics-assignment python runner_planner.py --seed 42 --planner dijkstra
    conda run -n robotics-assignment python runner_planner.py --seed 42 --planner astar
    conda run -n robotics-assignment python runner_planner.py --seed 42 --planner wastar3
    conda run -n robotics-assignment python runner_planner.py --seed 42 --planner wastar10

runner.py and all existing files are NOT modified.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from maze.generator      import MazeGrid
from navigation.occupancy_grid import OccupancyGrid
from navigation.planner  import plan, plan_dijkstra, plan_weighted_astar
import runner as _runner


# ── Snap planner waypoints to maze corridor centres ───────────────────────────

def _snap_to_corridors(
    path:  list[tuple[float, float]],
    pitch: float,
) -> list[tuple[float, float]]:
    """
    Each coordinate is snapped to the nearest multiple of `pitch` (0, pitch,
    2*pitch, ...).  This corrects the 0.05 m offset introduced by the 0.1 m
    occupancy grid and removes sub-corridor micro-steps from Weighted A*.
    After snapping, consecutive duplicate waypoints are removed.
    """
    def snap(v: float) -> float:
        return round(round(v / pitch) * pitch, 6)

    snapped: list[tuple[float, float]] = []
    for x, y in path:
        pt = (snap(x), snap(y))
        if not snapped or pt != snapped[-1]:
            snapped.append(pt)
    return snapped


# ── Thin wrapper around runner.run_episode ────────────────────────────────────

def run_with_planner(
    seed:       int,
    grid_size:  int   = 10,
    planner:    str   = "astar",
    max_time:   float = 300.0,
    visualize:  bool  = True,
    speed:      float = 2.0,
    demo:       bool  = False,
) -> dict:
    """
    Build the planner path, snap it to corridor centres, then monkey-patch
    MazeGrid.solution_world_xy so that runner.run_episode uses it.
    runner.py is never modified.
    """
    # 1. Build maze + occupancy grid (mirrors what runner.py does internally)
    maze = MazeGrid(seed=seed, grid_size=grid_size)
    xmax = grid_size * maze.pitch + 1.0
    occ  = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=xmax,
                         y_min=-1.0, y_max=xmax)
    occ.load_from_maze(maze)
    goal  = maze.cell_centre_world(*maze.goal_cell)
    start = (0.0, 0.0)

    # 2. Choose and run the planner
    _w_map = {"wastar3": 3.0, "wastar10": 10.0}
    if planner == "dijkstra":
        raw_path = plan_dijkstra(occ, start, goal, center_weight=2.0)
    elif planner in _w_map:
        raw_path = plan_weighted_astar(occ, start, goal,
                                       center_weight=2.0, w=_w_map[planner])
    else:
        raw_path = plan(occ, start, goal, center_weight=2.0)

    if not raw_path:
        print(f"[runner_planner] Planner '{planner}' found no path — falling back to maze solution.")
        return _runner.run_episode(seed=seed, grid_size=grid_size,
                                   max_time=max_time, visualize=visualize,
                                   speed=speed, demo=demo)

    # 3. Snap to corridor centres
    snapped = _snap_to_corridors(raw_path, pitch=maze.pitch)
    print(f"\n[runner_planner] planner={planner}  "
          f"raw_waypoints={len(raw_path)}  snapped_waypoints={len(snapped)}")
    print(f"  first 5 snapped: {snapped[:5]}")
    print(f"  last  2 snapped: {snapped[-2:]}\n")

    # 4. Monkey-patch MazeGrid.solution_world_xy to return the snapped path.
    #    runner.run_episode calls maze_grid.solution_world_xy() internally;
    #    we redirect it so the robot follows the planner's route.
    _original = MazeGrid.solution_world_xy

    def _patched(self):                        # noqa: ANN001
        return snapped

    MazeGrid.solution_world_xy = _patched      # type: ignore[method-assign]

    try:
        result = _runner.run_episode(
            seed=seed, grid_size=grid_size,
            max_time=max_time, visualize=visualize,
            speed=speed, demo=demo,
        )
    finally:
        MazeGrid.solution_world_xy = _original  # always restore

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Navigate with a chosen path planner (runner.py untouched)."
    )
    parser.add_argument("--seed",      type=int,   default=42)
    parser.add_argument("--grid-size", type=int,   default=10)
    parser.add_argument("--planner",
                        choices=["astar", "dijkstra", "wastar3", "wastar10"],
                        default="astar")
    parser.add_argument("--max-time",  type=float, default=300.0)
    parser.add_argument("--no-viz",    action="store_true")
    parser.add_argument("--speed",     type=float, default=2.0)
    parser.add_argument("--demo",      action="store_true")
    args = parser.parse_args()

    run_with_planner(
        seed=args.seed,
        grid_size=args.grid_size,
        planner=args.planner,
        max_time=args.max_time,
        visualize=not args.no_viz,
        speed=args.speed,
        demo=args.demo,
    )


if __name__ == "__main__":
    main()
