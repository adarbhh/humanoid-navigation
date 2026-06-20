import sys
sys.path.insert(0, '.')
from maze.generator import MazeGrid
from navigation.occupancy_grid import OccupancyGrid
from navigation.planner import plan, plan_dijkstra

maze = MazeGrid(seed=42, grid_size=10)
occ_raw = OccupancyGrid(resolution=0.1, x_min=-1, x_max=16, y_min=-1, y_max=16)
occ_raw.load_from_maze(maze)

goal = maze.cell_centre_world(*maze.goal_cell)
sol  = [(float(x), float(y)) for x, y in maze.solution_world_xy()]

sr, sc = occ_raw.world_to_cell(0.0, 0.0)
gr, gc = occ_raw.world_to_cell(*goal)
print(f"Start cell ({sr},{sc}) occupied={occ_raw.grid[sr,sc]!=0}")
print(f"Goal  cell ({gr},{gc}) occupied={occ_raw.grid[gr,gc]!=0}")
print(f"Goal world: {goal}")
print(f"solution_world_xy: {len(sol)} waypoints, first3={sol[:3]}, last={sol[-1]}")

astar = plan(occ_raw, (0.0, 0.0), goal, center_weight=2.0)
dijk  = plan_dijkstra(occ_raw, (0.0, 0.0), goal, center_weight=2.0)
print(f"A*:       {len(astar)} waypoints, first3={astar[:3]}, last={astar[-1] if astar else None}")
print(f"Dijkstra: {len(dijk)}  waypoints, first3={dijk[:3]},  last={dijk[-1] if dijk else None}")
