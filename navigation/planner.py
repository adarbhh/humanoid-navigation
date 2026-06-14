"""
A* global planner on an OccupancyGrid with corridor-centering cost.

A distance-transform penalty is added to each cell's edge cost so A* prefers
cells that are far from walls.  The result is a path through the centre of
corridors rather than one that hugs walls.

Path simplification removes collinear intermediate waypoints, keeping only
turn points and endpoints.  This gives a small set of clean waypoints that
the pure-pursuit controller can follow precisely.
"""

from __future__ import annotations

import heapq

import numpy as np

from navigation.occupancy_grid import OccupancyGrid

# 8-connected moves: (drow, dcol, euclidean_cost_multiplier)
_MOVES = [
    (-1,  0, 1.0), ( 1,  0, 1.0), ( 0, -1, 1.0), ( 0,  1, 1.0),
    (-1, -1, 1.414), (-1,  1, 1.414), ( 1, -1, 1.414), ( 1,  1, 1.414),
]


def plan(
    grid:          OccupancyGrid,
    start_world:   tuple[float, float],
    goal_world:    tuple[float, float],
    center_weight: float = 4.0,
) -> list[tuple[float, float]]:
    """
    A* on the occupancy grid with corridor-centering cost.

    center_weight scales the distance-transform penalty.  Higher values push
    the path further from walls at the cost of a slightly longer route.
    Returns simplified world-coordinate waypoints (turn points only).
    Returns [] if no path exists.

    Pass an inflated grid so the path already has robot-footprint clearance;
    the centering cost then pushes it to the centre of the remaining free space.
    """
    sr, sc = grid.world_to_cell(*start_world)
    gr, gc = grid.world_to_cell(*goal_world)

    if not grid.in_bounds(sr, sc) or not grid.in_bounds(gr, gc):
        return []

    dist_map = grid.distance_transform()          # metres from nearest wall
    max_dist = float(dist_map.max()) or 1.0       # normalisation denominator

    def h(r: int, c: int) -> float:
        return np.hypot(r - gr, c - gc) * grid.res

    def edge_cost(r: int, c: int, mult: float) -> float:
        # Base move cost + wall-proximity penalty.
        # wall_prox: 1.0 = right against inflated wall, 0.0 = corridor centre.
        # Scaling by grid.res keeps units consistent with move distance.
        wall_prox = 1.0 - dist_map[r, c] / max_dist
        return mult * grid.res + center_weight * wall_prox * grid.res

    open_heap: list = [(h(sr, sc), 0.0, sr, sc)]
    parent:  dict[tuple[int, int], tuple[int, int] | None] = {(sr, sc): None}
    g_score: dict[tuple[int, int], float]                  = {(sr, sc): 0.0}
    closed:  set[tuple[int, int]]                          = set()

    while open_heap:
        _f, g, r, c = heapq.heappop(open_heap)

        if (r, c) in closed:
            continue
        closed.add((r, c))

        if r == gr and c == gc:
            dense = _reconstruct(parent, grid, (gr, gc))
            return _simplify(dense)

        for dr, dc, mult in _MOVES:
            nr, nc = r + dr, c + dc
            if not grid.in_bounds(nr, nc):
                continue
            if grid.grid[nr, nc] == OccupancyGrid.OCCUPIED:
                continue
            if (nr, nc) in closed:
                continue
            ng = g + edge_cost(nr, nc, mult)
            if (nr, nc) not in g_score or ng < g_score[(nr, nc)]:
                g_score[(nr, nc)] = ng
                parent[(nr, nc)]  = (r, c)
                heapq.heappush(open_heap, (ng + h(nr, nc), ng, nr, nc))

    return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reconstruct(
    parent: dict[tuple[int, int], tuple[int, int] | None],
    grid:   OccupancyGrid,
    goal:   tuple[int, int],
) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    node: tuple[int, int] | None = goal
    while node is not None:
        path.append(grid.cell_to_world(*node))
        node = parent.get(node)
    path.reverse()
    return path


def _simplify(
    path:      list[tuple[float, float]],
    angle_tol: float = np.deg2rad(8),
) -> list[tuple[float, float]]:
    """
    Remove collinear intermediate waypoints, keeping only direction-change
    points and the start/goal.  Reduces a dense 500-point A* path to only
    the ~40 turn points the controller actually needs to follow.
    """
    if len(path) < 3:
        return path

    result = [path[0]]
    for i in range(1, len(path) - 1):
        p0 = result[-1]
        p1 = path[i]
        p2 = path[i + 1]
        d1 = np.arctan2(p1[1] - p0[1], p1[0] - p0[0])
        d2 = np.arctan2(p2[1] - p1[1], p2[0] - p1[0])
        diff = abs((d2 - d1 + np.pi) % (2 * np.pi) - np.pi)
        if diff > angle_tol:
            result.append(p1)

    result.append(path[-1])
    return result
