"""
Seeded procedural maze generator — Unitree G1 navigation assignment.

Algorithm:  Recursive-backtracker DFS (produces perfect mazes: exactly one
            path between any two cells; long winding corridors).

Wall map:   (2N+1)×(2N+1) boolean grid.
              wall_map[gr][gc] = True  -> solid material
              wall_map[gr][gc] = False -> open space
            Even indices = wall material; odd indices = passable corridor.
            Corner cells (even,even) are ALWAYS solid -> no inter-wall gaps.

Coordinates: World origin at the centre of start cell (0,0).
             +x = east (column direction)
             +y = north (row direction)
             +z = up

Usage (CLI):
    python -m maze.generator --seed 42
    python -m maze.generator --seed 42 --difficulty hard
    python -m maze.generator --seed 42 --grid-size 12 --corridor-width 1.1
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).parent.parent

# ── G1 physical parameters ────────────────────────────────────────────────────
G1_BODY_WIDTH_M   = 0.45    # shoulder-to-shoulder width
G1_BODY_DEPTH_M   = 0.38    # front-to-back depth
G1_PELVIS_Z_M     = 0.793   # pelvis height in default standing pose (from g1.xml keyframe)
MIN_CORRIDOR_M    = G1_BODY_WIDTH_M * 2.0   # must allow 180° turn in place

# ── Difficulty presets ────────────────────────────────────────────────────────
DIFFICULTY_PRESETS = {
    "easy":   {"grid_size":  6, "corridor_width": 1.4},
    "medium": {"grid_size": 10, "corridor_width": 1.2},
    "hard":   {"grid_size": 15, "corridor_width": 1.0},
}

# ── Appearance ────────────────────────────────────────────────────────────────
WALL_RGBA  = [0.65, 0.50, 0.35, 1.0]   # sandstone
START_RGBA = [0.10, 0.80, 0.10, 0.80]  # green
GOAL_RGBA  = [0.80, 0.10, 0.10, 0.80]  # red


# ═════════════════════════════════════════════════════════════════════════════
class MazeGrid:
    """
    Pure maze data structure — no MuJoCo dependency.

    Attributes
    ----------
    wall_map        (2N+1)×(2N+1) bool grid; True = solid
    solution_cells  list of (row, col) from start to goal (BFS optimal)
    """

    def __init__(
        self,
        seed:           int,
        grid_size:      int   = 8,
        corridor_width: float = 1.2,
        wall_thickness: float = 0.15,
        wall_height:    float = 2.0,
    ):
        # ── Validation ────────────────────────────────────────────────────────
        if corridor_width < MIN_CORRIDOR_M:
            raise ValueError(
                f"corridor_width={corridor_width:.2f} m is too narrow for the G1. "
                f"Minimum is {MIN_CORRIDOR_M:.2f} m (2 × shoulder width {G1_BODY_WIDTH_M:.2f} m)."
            )
        if grid_size < 3:
            raise ValueError(f"grid_size must be ≥ 3, got {grid_size}.")

        self.seed           = seed
        self.N              = grid_size
        self.corridor_width = corridor_width
        self.wall_thickness = wall_thickness
        self.wall_height    = wall_height
        self.pitch          = corridor_width + wall_thickness  # cell centre-to-centre

        # ── Build (2N+1)×(2N+1) wall map ─────────────────────────────────────
        G = 2 * grid_size + 1
        self.wall_map: List[List[bool]] = [[True] * G for _ in range(G)]

        # Open every cell centre — they are never walls
        for r in range(grid_size):
            for c in range(grid_size):
                self.wall_map[2*r + 1][2*c + 1] = False

        # Carve passages via DFS
        rng = random.Random(seed)
        self._carve(rng)

        # ── BFS solution ──────────────────────────────────────────────────────
        self.start_cell = (0, 0)
        self.goal_cell  = (grid_size - 1, grid_size - 1)
        self.solution_cells: List[Tuple[int, int]] = self._bfs()
        assert self.solution_cells, (
            "BFS returned no solution — perfect-maze invariant violated."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Maze generation
    # ─────────────────────────────────────────────────────────────────────────

    def _carve(self, rng: random.Random) -> None:
        """Recursive-backtracker DFS. Opens walls between visited cells."""
        N = self.N
        visited = [[False] * N for _ in range(N)]
        stack   = [(0, 0)]
        visited[0][0] = True

        while stack:
            r, c = stack[-1]
            unvisited_nbrs = [
                (nr, nc)
                for (nr, nc) in [(r-1, c), (r+1, c), (r, c-1), (r, c+1)]
                if 0 <= nr < N and 0 <= nc < N and not visited[nr][nc]
            ]
            if unvisited_nbrs:
                nr, nc = rng.choice(unvisited_nbrs)
                # Open the wall between (r,c) and (nr,nc) in wall_map
                # Wall cell index = (r+nr+1, c+nc+1) — midpoint in expanded grid
                self.wall_map[r + nr + 1][c + nc + 1] = False
                visited[nr][nc] = True
                stack.append((nr, nc))
            else:
                stack.pop()

    # ─────────────────────────────────────────────────────────────────────────
    # BFS solver
    # ─────────────────────────────────────────────────────────────────────────

    def _bfs(self) -> List[Tuple[int, int]]:
        """BFS from start to goal. Returns cell path."""
        queue   = deque([(self.start_cell, [self.start_cell])])
        visited = {self.start_cell}
        N       = self.N

        while queue:
            (r, c), path = queue.popleft()
            if (r, c) == self.goal_cell:
                return path
            for (nr, nc) in [(r-1, c), (r+1, c), (r, c-1), (r, c+1)]:
                if 0 <= nr < N and 0 <= nc < N and (nr, nc) not in visited:
                    if not self.wall_map[r + nr + 1][c + nc + 1]:   # passage is open
                        visited.add((nr, nc))
                        queue.append(((nr, nc), path + [(nr, nc)]))
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # World-coordinate helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _grid_cell_geom(
        self, gr: int, gc: int
    ) -> Tuple[float, float, float, float]:
        """
        (x_centre, y_centre, half_x, half_y) for wall-map cell [gr][gc].
        World origin = centre of start cell (0, 0).
        """
        C = self.corridor_width
        T = self.wall_thickness
        P = self.pitch
        # Shift so that start cell (wall_map[1][1]) is at world origin
        origin = -(T + C / 2)

        x_left = origin + (gc // 2) * P + (T if gc % 2 == 1 else 0)
        half_x = (C if gc % 2 == 1 else T) / 2

        y_bot  = origin + (gr // 2) * P + (T if gr % 2 == 1 else 0)
        half_y = (C if gr % 2 == 1 else T) / 2

        return x_left + half_x, y_bot + half_y, half_x, half_y

    def cell_centre_world(self, r: int, c: int) -> Tuple[float, float]:
        """World (x, y) of the centre of cell (row r, col c)."""
        x, y, _, _ = self._grid_cell_geom(2*r + 1, 2*c + 1)
        return x, y

    def solution_world_xy(self) -> List[Tuple[float, float]]:
        """Solution path as a list of world (x, y) waypoints."""
        return [self.cell_centre_world(r, c) for r, c in self.solution_cells]

    def optimal_path_length_m(self) -> float:
        """Euclidean length of the BFS-optimal path (metres)."""
        return (len(self.solution_cells) - 1) * self.pitch

    def maze_footprint_m(self) -> Tuple[float, float]:
        """Total (width, depth) of the maze boundary in metres."""
        side = self.N * self.pitch + self.wall_thickness
        return side, side

    # ─────────────────────────────────────────────────────────────────────────
    # Serialisation
    # ─────────────────────────────────────────────────────────────────────────

    def to_solution_dict(self) -> dict:
        """Return all solution metadata as a JSON-serialisable dict."""
        sx, sy = self.cell_centre_world(*self.start_cell)
        gx, gy = self.cell_centre_world(*self.goal_cell)
        return {
            "seed":                  self.seed,
            "grid_size":             self.N,
            "corridor_width_m":      self.corridor_width,
            "wall_thickness_m":      self.wall_thickness,
            "wall_height_m":         self.wall_height,
            "cell_pitch_m":          self.pitch,
            "start_cell":            list(self.start_cell),
            "goal_cell":             list(self.goal_cell),
            "start_world_xy_m":      [round(sx, 4), round(sy, 4)],
            "goal_world_xy_m":       [round(gx, 4), round(gy, 4)],
            "solution_cells":        [list(p) for p in self.solution_cells],
            "solution_world_xy_m":   [[round(x, 4), round(y, 4)]
                                      for x, y in self.solution_world_xy()],
            "optimal_path_length_m": round(self.optimal_path_length_m(), 4),
            "n_solution_steps":      len(self.solution_cells) - 1,
            "maze_footprint_m":      [round(v, 4) for v in self.maze_footprint_m()],
            "g1_body_width_m":       G1_BODY_WIDTH_M,
            "clearance_each_side_m": round((self.corridor_width - G1_BODY_WIDTH_M) / 2, 4),
        }

    @staticmethod
    def _wall_name(gr: int, gc: int) -> str:
        """Human-readable geom name for wall-map cell (gr, gc)."""
        if gr % 2 == 0 and gc % 2 == 0:
            return f"corner_{gr//2}_{gc//2}"
        elif gr % 2 == 0:
            return f"hwall_{gr//2}_{gc//2}"   # horizontal slab — blocks N/S
        elif gc % 2 == 0:
            return f"vwall_{gr//2}_{gc//2}"   # vertical slab   — blocks E/W
        return f"cell_{gr//2}_{gc//2}"         # always open, never reached


# ═════════════════════════════════════════════════════════════════════════════
class MazeScene:
    """
    Builds a MuJoCo scene from a MazeGrid using MjSpec (programmatic API).
    Avoids all XML include-path issues; produces a fully self-contained model.
    """

    def __init__(self, grid: MazeGrid, g1_scene_path: Path):
        self.grid         = grid
        self.g1_scene_path = Path(g1_scene_path).resolve()

    def build(self):
        """
        Load G1 base scene, inject maze walls + markers, return compiled MjModel.
        Also returns the MjSpec so callers can call spec.to_xml() for saving.
        """
        import mujoco

        spec = mujoco.MjSpec.from_file(str(self.g1_scene_path))
        grid = self.grid
        G    = 2 * grid.N + 1
        H    = grid.wall_height

        wb = spec.worldbody   # MjsBody — the root worldbody

        # ── Maze walls ────────────────────────────────────────────────────────
        for gr in range(G):
            for gc in range(G):
                if grid.wall_map[gr][gc]:
                    x, y, hx, hy = grid._grid_cell_geom(gr, gc)
                    g = wb.add_geom()
                    g.name      = grid._wall_name(gr, gc)
                    g.type      = mujoco.mjtGeom.mjGEOM_BOX
                    g.size      = [hx, hy, H / 2]
                    g.pos       = [x, y, H / 2]
                    g.rgba      = WALL_RGBA
                    g.contype   = 1
                    g.conaffinity = 1

        # ── Start marker (green disc) ─────────────────────────────────────────
        sx, sy = grid.cell_centre_world(*grid.start_cell)
        s_start = wb.add_site()
        s_start.name  = "start"
        s_start.type  = mujoco.mjtGeom.mjGEOM_CYLINDER
        s_start.size  = [0.28, 0.28, 0.01]
        s_start.pos   = [sx, sy, 0.01]
        s_start.rgba  = START_RGBA

        # ── Goal marker (red disc) ────────────────────────────────────────────
        gx, gy = grid.cell_centre_world(*grid.goal_cell)
        s_goal = wb.add_site()
        s_goal.name  = "goal"
        s_goal.type  = mujoco.mjtGeom.mjGEOM_CYLINDER
        s_goal.size  = [0.28, 0.28, 0.01]
        s_goal.pos   = [gx, gy, 0.01]
        s_goal.rgba  = GOAL_RGBA

        model = spec.compile()
        return model, spec

    def n_wall_geoms(self) -> int:
        """Count of solid cells in wall_map."""
        g = self.grid
        G = 2 * g.N + 1
        return sum(g.wall_map[gr][gc] for gr in range(G) for gc in range(G))


# ═════════════════════════════════════════════════════════════════════════════
# Visualiser
# ═════════════════════════════════════════════════════════════════════════════

def visualize_maze(grid: MazeGrid, out_path: Path) -> None:
    """Render maze + solution path to a PNG using matplotlib."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    G  = 2 * grid.N + 1
    C  = grid.corridor_width
    T  = grid.wall_thickness
    P  = grid.pitch
    origin_shift = -(T + C / 2)
    w, h = grid.maze_footprint_m()

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_facecolor("#D5C5A1")

    # Background (maze footprint)
    ax.add_patch(patches.Rectangle(
        (origin_shift, origin_shift), w, h,
        facecolor="#F5ECD7", edgecolor="none", zorder=0
    ))

    # Wall cells
    for gr in range(G):
        for gc in range(G):
            if grid.wall_map[gr][gc]:
                x, y, hx, hy = grid._grid_cell_geom(gr, gc)
                ax.add_patch(patches.Rectangle(
                    (x - hx, y - hy), 2 * hx, 2 * hy,
                    facecolor="#7B5E2A", edgecolor="none", zorder=1
                ))

    # Solution path
    sol = grid.solution_world_xy()
    if len(sol) >= 2:
        xs, ys = zip(*sol)
        ax.plot(xs, ys, "-", color="#E74C3C", linewidth=2.0, zorder=3, alpha=0.85)
        ax.plot(xs, ys, "o", color="#E74C3C", markersize=3,  zorder=3, alpha=0.6)

    # Start / goal markers
    sx, sy = grid.cell_centre_world(*grid.start_cell)
    gx, gy = grid.cell_centre_world(*grid.goal_cell)
    ax.plot(sx, sy, "o", color="#27AE60", markersize=12, zorder=4)
    ax.plot(gx, gy, "*", color="#E74C3C", markersize=16, zorder=4)
    ax.text(sx, sy, "S", ha="center", va="center",
            fontsize=7, fontweight="bold", color="white", zorder=5)
    ax.text(gx, gy, "G", ha="center", va="center",
            fontsize=7, fontweight="bold", color="white", zorder=5)

    ax.set_xlim(origin_shift - 0.2, origin_shift + w + 0.2)
    ax.set_ylim(origin_shift - 0.2, origin_shift + h + 0.2)
    ax.set_title(
        f"Seed {grid.seed}  |  {grid.N}×{grid.N} grid  |  "
        f"corridor {grid.corridor_width:.1f} m  |  "
        f"optimal path {grid.optimal_path_length_m():.1f} m  |  "
        f"{grid.n_solution_steps if hasattr(grid,'n_solution_steps') else len(grid.solution_cells)-1} steps",
        fontsize=9, pad=6
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Public entry point
# ═════════════════════════════════════════════════════════════════════════════

def generate(
    seed:           int,
    grid_size:      int   = 8,
    corridor_width: float = 1.2,
    wall_thickness: float = 0.15,
    wall_height:    float = 2.0,
    out_dir:        Optional[Path] = None,
    g1_scene:       Optional[Path] = None,
    visualize:      bool = True,
    quiet:          bool = False,
) -> Tuple["MazeGrid", Path]:
    """
    Generate a maze, compile the MuJoCo scene, write outputs.

    Returns
    -------
    (grid, out_dir)  — the MazeGrid object and the output directory path.

    Output files
    ------------
    <out_dir>/solution.json     — ground-truth solution + metadata
    <out_dir>/maze_scene.xml    — complete MuJoCo XML (for inspection / viewer)
    <out_dir>/maze_viz.png      — 2-D visualisation
    """
    grid = MazeGrid(
        seed           = seed,
        grid_size      = grid_size,
        corridor_width = corridor_width,
        wall_thickness = wall_thickness,
        wall_height    = wall_height,
    )

    if out_dir is None:
        out_dir = ROOT / "mazes" / f"seed{seed:05d}_size{grid_size:02d}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if g1_scene is None:
        g1_scene = ROOT / "robot" / "model" / "g1" / "scene.xml"

    # 1. Solution JSON
    sol_path = out_dir / "solution.json"
    sol_path.write_text(json.dumps(grid.to_solution_dict(), indent=2))

    # 2. MuJoCo scene — compile via MjSpec, then export XML for inspection
    scene       = MazeScene(grid, g1_scene)
    model, spec = scene.build()
    xml_path    = out_dir / "maze_scene.xml"
    xml_path.write_text(spec.to_xml(), encoding="utf-8")

    # 3. PNG visualisation
    if visualize:
        viz_path = out_dir / "maze_viz.png"
        visualize_maze(grid, viz_path)

    if not quiet:
        w, h = grid.maze_footprint_m()
        n_walls = scene.n_wall_geoms()
        print(f"Maze generated:")
        print(f"  seed={seed}  grid={grid_size}x{grid_size}  "
              f"corridor={corridor_width:.2f} m  wall={wall_thickness:.2f} m")
        print(f"  footprint: {w:.2f} x {h:.2f} m")
        print(f"  wall geoms: {n_walls}")
        print(f"  optimal path: {grid.optimal_path_length_m():.2f} m  "
              f"({len(grid.solution_cells)-1} steps)")
        print(f"  clearance each side: "
              f"{(corridor_width - G1_BODY_WIDTH_M)/2:.2f} m "
              f"(G1 width {G1_BODY_WIDTH_M:.2f} m)")
        print(f"  outputs -> {out_dir}/")

    return grid, out_dir


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate a seeded MuJoCo maze for G1 navigation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--seed",           type=int,   required=True,
                   help="RNG seed — same seed -> identical maze")
    p.add_argument("--difficulty",     choices=DIFFICULTY_PRESETS.keys(),
                   help="Preset difficulty (overrides --grid-size / --corridor-width)")
    p.add_argument("--grid-size",      type=int,   default=8,
                   help="N×N grid (≥3)")
    p.add_argument("--corridor-width", type=float, default=1.2,
                   help=f"Corridor width in metres (min {MIN_CORRIDOR_M:.2f} for G1)")
    p.add_argument("--wall-thickness", type=float, default=0.15)
    p.add_argument("--wall-height",    type=float, default=2.0)
    p.add_argument("--out-dir",        type=Path,  default=None,
                   help="Output directory (default: mazes/seed<N>_size<M>/)")
    p.add_argument("--no-viz",         action="store_true",
                   help="Skip PNG visualisation")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()

    kwargs: dict = {
        "seed":           args.seed,
        "wall_thickness": args.wall_thickness,
        "wall_height":    args.wall_height,
        "out_dir":        args.out_dir,
        "visualize":      not args.no_viz,
    }
    if args.difficulty:
        kwargs.update(DIFFICULTY_PRESETS[args.difficulty])
    else:
        kwargs["grid_size"]      = args.grid_size
        kwargs["corridor_width"] = args.corridor_width

    try:
        grid, out = generate(**kwargs)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
