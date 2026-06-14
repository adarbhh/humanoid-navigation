"""
2-D occupancy grid for maze navigation.

Cells are stored as uint8:
  FREE     = 0
  OCCUPIED = 100
  UNKNOWN  = 50

Resolution is 0.1 m/cell.  Grid covers the full maze plus a 1 m border.
"""

from __future__ import annotations

import numpy as np


class OccupancyGrid:
    FREE     = np.uint8(0)
    OCCUPIED = np.uint8(100)
    UNKNOWN  = np.uint8(50)

    def __init__(
        self,
        resolution: float = 0.1,
        x_min: float = -1.0,
        x_max: float = 16.0,
        y_min: float = -1.0,
        y_max: float = 16.0,
    ) -> None:
        self.res   = resolution
        self.x_min = x_min
        self.y_min = y_min
        self.W     = int(np.ceil((x_max - x_min) / resolution))
        self.H     = int(np.ceil((y_max - y_min) / resolution))
        self.grid  = np.full((self.H, self.W), self.UNKNOWN, dtype=np.uint8)

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        col = int((x - self.x_min) / self.res)
        row = int((y - self.y_min) / self.res)
        return row, col

    def cell_to_world(self, row: int, col: int) -> tuple[float, float]:
        x = self.x_min + (col + 0.5) * self.res
        y = self.y_min + (row + 0.5) * self.res
        return x, y

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.H and 0 <= col < self.W

    # ── Map loading ───────────────────────────────────────────────────────────

    def load_from_maze(self, maze_grid) -> None:
        """
        Pre-populate from the known MazeGrid wall map.
        All corridor cells = FREE; all solid wall cells = OCCUPIED.
        This gives A* a perfect map to plan on without using GT pose.
        """
        g = maze_grid
        N = g.N
        self.grid[:] = self.FREE

        for gr in range(2 * N + 1):
            for gc in range(2 * N + 1):
                if not g.wall_map[gr][gc]:
                    continue
                xc, yc, hx, hy = g._grid_cell_geom(gr, gc)
                r0, c0 = self.world_to_cell(xc - hx, yc - hy)
                r1, c1 = self.world_to_cell(xc + hx, yc + hy)
                r0 = max(0, r0);  c0 = max(0, c0)
                r1 = min(self.H - 1, r1);  c1 = min(self.W - 1, c1)
                self.grid[r0 : r1 + 1, c0 : c1 + 1] = self.OCCUPIED

    def distance_transform(self) -> np.ndarray:
        """
        Euclidean distance transform of the free space.
        Returns an (H, W) float32 array where each cell's value is its distance
        (in metres) to the nearest OCCUPIED cell.  OCCUPIED cells are 0.
        Used by the planner to add a corridor-centering cost.
        """
        from scipy.ndimage import distance_transform_edt
        free_mask = self.grid != self.OCCUPIED
        # distance_transform_edt returns distances in pixels; multiply by res for metres
        return (distance_transform_edt(free_mask) * self.res).astype(np.float32)

    def inflated(self, radius_cells: int) -> "OccupancyGrid":
        """Return a copy with obstacles expanded by radius_cells (robot footprint)."""
        from scipy.ndimage import binary_dilation
        occ  = self.grid == self.OCCUPIED
        kern = np.ones((2 * radius_cells + 1, 2 * radius_cells + 1), dtype=bool)
        expanded = binary_dilation(occ, structure=kern)
        new = OccupancyGrid(
            self.res,
            self.x_min, self.x_min + self.W * self.res,
            self.y_min, self.y_min + self.H * self.res,
        )
        new.grid[:] = self.grid
        new.grid[expanded] = self.OCCUPIED
        return new

    # ── LiDAR update ─────────────────────────────────────────────────────────

    def update_from_lidar(
        self,
        robot_x: float,
        robot_y: float,
        robot_theta: float,
        ranges: np.ndarray,
        angles: np.ndarray,
        min_range: float = 0.15,
        max_range: float = 9.9,
    ) -> None:
        """Ray-cast LiDAR beams: mark free cells along each ray, occupied at endpoint."""
        for r, a in zip(ranges, angles):
            if r < min_range or not np.isfinite(r):
                continue
            world_angle = robot_theta + a
            hit     = r < max_range
            end_r   = r if hit else max_range
            end_x   = robot_x + end_r * np.cos(world_angle)
            end_y   = robot_y + end_r * np.sin(world_angle)
            self._cast_ray(robot_x, robot_y, end_x, end_y, hit)

    def _cast_ray(
        self, x0: float, y0: float, x1: float, y1: float, mark_hit: bool
    ) -> None:
        """Bresenham ray from (x0,y0) to (x1,y1). Mark free along ray, occupied at end."""
        r0, c0 = self.world_to_cell(x0, y0)
        r1, c1 = self.world_to_cell(x1, y1)

        dr = abs(r1 - r0);  sr = 1 if r1 >= r0 else -1
        dc = abs(c1 - c0);  sc = 1 if c1 >= c0 else -1
        err = dr - dc
        r, c = r0, c0

        for _ in range(max(dr, dc) + 2):
            at_end = (r == r1 and c == c1)
            if self.in_bounds(r, c):
                if at_end and mark_hit:
                    self.grid[r, c] = self.OCCUPIED
                elif not at_end and self.grid[r, c] != self.OCCUPIED:
                    self.grid[r, c] = self.FREE
            if at_end:
                break
            e2 = 2 * err
            if e2 > -dc:
                err -= dc;  r += sr
            if e2 < dr:
                err += dr;  c += sc
