import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import sys
sys.path.insert(0, ".")
from maze.generator import MazeGrid
from navigation.occupancy_grid import OccupancyGrid
from navigation.planner import plan, plan_dijkstra

maze = MazeGrid(seed=42, grid_size=50)
xmax = 50 * 1.35 + 1.0
occ = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=xmax, y_min=-1.0, y_max=xmax)
occ.load_from_maze(maze)

goal  = maze.cell_centre_world(*maze.goal_cell)
start = (0.0, 0.0)

path_astar    = plan(occ, start, goal, center_weight=0.0)
path_dijkstra = plan_dijkstra(occ, start, goal, center_weight=0.0)

fig, ax = plt.subplots(figsize=(14, 14), facecolor="#1a1a2e")
ax.set_facecolor("#1a1a2e")

# Draw walls
grid = occ.grid
rows, cols = grid.shape
wall_xs, wall_ys = [], []
for r in range(rows):
    for c in range(cols):
        if grid[r, c] == 1:
            wx, wy = occ.cell_to_world(r, c)
            wall_xs.append(wx)
            wall_ys.append(wy)
ax.scatter(wall_xs, wall_ys, s=1.5, c="#d0d0d0", marker="s", linewidths=0)

# Dijkstra path (orange dashed, under)
if path_dijkstra:
    xs = [p[0] for p in path_dijkstra]
    ys = [p[1] for p in path_dijkstra]
    ax.plot(xs, ys, color="#ff9500", linewidth=3, alpha=0.8,
            linestyle="--", label=f"Dijkstra  ({len(path_dijkstra)} waypoints)", zorder=2)

# A* path (blue, over)
if path_astar:
    xs = [p[0] for p in path_astar]
    ys = [p[1] for p in path_astar]
    ax.plot(xs, ys, color="#0071e3", linewidth=2, alpha=0.9,
            label=f"A*  ({len(path_astar)} waypoints)", zorder=3)

ax.plot(*start, "o", color="#30d158", markersize=14, zorder=5, label="Start")
ax.plot(*goal,  "*", color="#ff375f", markersize=18, zorder=5, label="Goal")

ax.set_xlim(-1.0, xmax)
ax.set_ylim(-1.0, xmax)
ax.set_aspect("equal")
ax.axis("off")

ax.legend(loc="upper right", fontsize=13, framealpha=0.85,
          facecolor="#1a1a2e", edgecolor="#555", labelcolor="white")

ax.set_title(
    "50x50 Maze  |  A* vs Dijkstra find identical paths\n"
    "Maze corridors eliminate A*'s heuristic advantage",
    color="white", fontsize=15, fontweight="bold", pad=14
)

plt.tight_layout()
plt.savefig("report/maze_50x50_comparison.png", dpi=150,
            bbox_inches="tight", facecolor="#1a1a2e")
print("Saved report/maze_50x50_comparison.png")
print(f"A* waypoints: {len(path_astar)}  |  Dijkstra waypoints: {len(path_dijkstra)}")
print(f"Paths identical: {path_astar == path_dijkstra}")
