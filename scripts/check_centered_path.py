import sys; sys.path.insert(0, '.')
from maze.generator import MazeGrid
from navigation.occupancy_grid import OccupancyGrid
from navigation.planner import plan
import numpy as np

grid  = MazeGrid(seed=42)
occ   = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=16.0, y_min=-1.0, y_max=16.0)
occ.load_from_maze(grid)
occ_nav = occ.inflated(3)

goal = grid.cell_centre_world(*grid.goal_cell)
path = plan(occ_nav, (0.0, 0.0), goal, center_weight=4.0)
print(f"{len(path)} waypoints (centered A*)")
for i, (x, y) in enumerate(path[:10]):
    print(f"  wp[{i:2d}]  ({x:6.3f}, {y:6.3f})")

sol = list(grid.solution_world_xy())
print(f"\ncell centres (first 10 of {len(sol)}):")
for i, (x, y) in enumerate(sol[:10]):
    print(f"  cc[{i:2d}]  ({x:6.3f}, {y:6.3f})")
