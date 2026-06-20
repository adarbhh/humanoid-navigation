import sys
sys.path.insert(0, '.')
import numpy as np
from maze.generator import MazeGrid
from navigation.occupancy_grid import OccupancyGrid
from navigation.planner import plan, plan_weighted_astar

maze = MazeGrid(seed=42, grid_size=10)
occ  = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=16.0, y_min=-1.0, y_max=16.0)
occ.load_from_maze(maze)
goal  = maze.cell_centre_world(*maze.goal_cell)
start = (0.0, 0.0)

sol   = [(float(x), float(y)) for x, y in maze.solution_world_xy()]
astar = plan(occ, start, goal, center_weight=2.0)
wa10  = plan_weighted_astar(occ, start, goal, center_weight=2.0, w=10)

print('solution_world_xy waypoints:')
for i, p in enumerate(sol): print(f'  {i:2d}: {p}')
print()
print('A* waypoints:')
for i, p in enumerate(astar): print(f'  {i:2d}: {p}')
print()
print('Weighted A* w=10 waypoints:')
for i, p in enumerate(wa10): print(f'  {i:2d}: {p}')
