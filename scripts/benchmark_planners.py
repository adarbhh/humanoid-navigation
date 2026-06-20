"""
Benchmark Dijkstra vs A* vs Weighted A* (w=3, w=10) across maze sizes.
No MuJoCo simulation — pure planning algorithm comparison.

Usage:
    conda run -n robotics-assignment python scripts/benchmark_planners.py
"""
import sys, time
import numpy as np
sys.path.insert(0, '.')

from maze.generator import MazeGrid
from navigation.occupancy_grid import OccupancyGrid
from navigation.planner import plan, plan_dijkstra, plan_weighted_astar


def path_len(pts):
    return sum(np.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
               for i in range(len(pts)-1))


PLANNERS = [
    ("Dijkstra",      lambda occ, s, g: plan_dijkstra(occ, s, g, center_weight=0.0)),
    ("A* (w=1)",      lambda occ, s, g: plan_weighted_astar(occ, s, g, center_weight=0.0, w=1)),
    ("Weighted A* w=3",  lambda occ, s, g: plan_weighted_astar(occ, s, g, center_weight=0.0, w=3)),
    ("Weighted A* w=10", lambda occ, s, g: plan_weighted_astar(occ, s, g, center_weight=0.0, w=10)),
]

SIZES = [10, 20, 50]
SEED  = 42
RUNS  = 3

print()
print(f"{'Planner':<22} {'Maze':>8}  {'Time(ms)':>9}  {'Path(m)':>8}  "
      f"{'vs Optimal':>10}  {'Waypoints':>9}  {'Speedup vs Dijk':>16}")
print("-" * 90)

for grid_size in SIZES:
    maze  = MazeGrid(seed=SEED, grid_size=grid_size)
    xmax  = grid_size * 1.35 + 1.0
    occ   = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=xmax,
                          y_min=-1.0, y_max=xmax)
    occ.load_from_maze(maze)
    goal  = maze.cell_centre_world(*maze.goal_cell)
    start = (0.0, 0.0)
    opt   = maze.optimal_path_length_m()

    baseline_ms = None
    for label, fn in PLANNERS:
        times = []
        for _ in range(RUNS):
            t0   = time.perf_counter()
            path = fn(occ, start, goal)
            times.append((time.perf_counter() - t0) * 1000)
        ms   = min(times)
        plen = path_len(path) if path else 0.0
        wp   = len(path)
        vs_opt = plen / opt if opt > 0 else 0

        if baseline_ms is None:
            baseline_ms = ms
        speedup = ms / baseline_ms  # <1 means faster than Dijkstra

        print(f"{label:<22} {grid_size:>4}x{grid_size:<4}  {ms:>9.1f}  {plen:>8.1f}  "
              f"{vs_opt:>9.3f}x  {wp:>9}  {speedup:>15.2f}x")
    print()

print("vs Optimal: how many times longer than the maze optimal path (1.000 = optimal)")
print("Speedup vs Dijk: time ratio vs Dijkstra (<1.0 = faster than Dijkstra)")
