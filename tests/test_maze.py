"""
Phase 2 test suite — maze generator.

Tests cover:
  - Determinism (same seed → identical wall map)
  - Seed independence (different seeds → different mazes)
  - Connectivity (BFS solution exists and is valid)
  - G1 physical fit (corridor width ≥ 2 × shoulder width)
  - Coordinate sanity (start at world origin, goal at correct offset)
  - MuJoCo compilation (generated scene loads without error)
  - Difficulty presets
  - Error handling (too-narrow corridor)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from maze.generator import (
    MazeGrid,
    MazeScene,
    DIFFICULTY_PRESETS,
    G1_BODY_WIDTH_M,
    MIN_CORRIDOR_M,
    generate,
)

G1_SCENE = ROOT / "robot" / "model" / "g1" / "scene.xml"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def grid_8x8():
    return MazeGrid(seed=42, grid_size=8)


@pytest.fixture(scope="module")
def grid_10x10():
    return MazeGrid(seed=42, grid_size=10)


# ── 1. Determinism ────────────────────────────────────────────────────────────

def test_same_seed_same_wall_map():
    """Identical seeds must produce byte-identical wall maps."""
    g1 = MazeGrid(seed=12345, grid_size=8)
    g2 = MazeGrid(seed=12345, grid_size=8)
    assert g1.wall_map == g2.wall_map, "Same seed produced different wall maps"


def test_same_seed_same_solution():
    """Identical seeds must produce identical solution paths."""
    g1 = MazeGrid(seed=12345, grid_size=8)
    g2 = MazeGrid(seed=12345, grid_size=8)
    assert g1.solution_cells == g2.solution_cells


def test_different_seeds_different_mazes():
    """Different seeds must (with overwhelming probability) produce different mazes."""
    grids = [MazeGrid(seed=s, grid_size=8) for s in [1, 2, 3, 100, 999]]
    maps  = [str(g.wall_map) for g in grids]
    assert len(set(maps)) == len(maps), "Two different seeds produced identical mazes"


def test_determinism_across_grid_sizes():
    """Seed is independent of grid size — each (seed, size) pair is unique."""
    g_small = MazeGrid(seed=42, grid_size=6)
    g_large = MazeGrid(seed=42, grid_size=10)
    # They can't share wall maps (different sizes), but both must be deterministic
    assert MazeGrid(seed=42, grid_size=6).wall_map  == g_small.wall_map
    assert MazeGrid(seed=42, grid_size=10).wall_map == g_large.wall_map


# ── 2. Structural integrity ───────────────────────────────────────────────────

def test_wall_map_dimensions(grid_8x8):
    """Wall map must be (2N+1)×(2N+1)."""
    N = grid_8x8.N
    G = 2 * N + 1
    assert len(grid_8x8.wall_map) == G
    assert all(len(row) == G for row in grid_8x8.wall_map)


def test_cell_centres_always_open(grid_8x8):
    """All cell-centre positions in the wall map must be open (False)."""
    N = grid_8x8.N
    for r in range(N):
        for c in range(N):
            assert not grid_8x8.wall_map[2*r+1][2*c+1], (
                f"Cell centre ({r},{c}) is marked as wall"
            )


def test_corners_always_solid(grid_8x8):
    """All corner positions (even,even) must be solid (True)."""
    N = grid_8x8.N
    G = 2 * N + 1
    for gr in range(0, G, 2):
        for gc in range(0, G, 2):
            assert grid_8x8.wall_map[gr][gc], (
                f"Corner ({gr},{gc}) is not solid"
            )


def test_outer_boundary_solid(grid_8x8):
    """The outer boundary row/col must be fully solid."""
    G = 2 * grid_8x8.N + 1
    for i in range(G):
        assert grid_8x8.wall_map[0][i],   f"South boundary open at col {i}"
        assert grid_8x8.wall_map[G-1][i], f"North boundary open at col {i}"
        assert grid_8x8.wall_map[i][0],   f"West boundary open at row {i}"
        assert grid_8x8.wall_map[i][G-1], f"East boundary open at row {i}"


def test_perfect_maze_no_isolated_cells(grid_8x8):
    """Every cell is reachable from every other (perfect maze property)."""
    N   = grid_8x8.N
    src = (0, 0)
    from collections import deque
    visited = {src}
    queue   = deque([src])
    while queue:
        r, c = queue.popleft()
        for nr, nc in [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]:
            if 0 <= nr < N and 0 <= nc < N and (nr,nc) not in visited:
                if not grid_8x8.wall_map[r+nr+1][c+nc+1]:
                    visited.add((nr, nc))
                    queue.append((nr, nc))
    assert len(visited) == N * N, (
        f"Only {len(visited)}/{N*N} cells reachable — maze is not connected"
    )


# ── 3. Solution path validity ─────────────────────────────────────────────────

def test_solution_exists(grid_8x8):
    assert grid_8x8.solution_cells, "No solution path found"


def test_solution_starts_and_ends_correctly(grid_8x8):
    sol = grid_8x8.solution_cells
    assert sol[0]  == grid_8x8.start_cell
    assert sol[-1] == grid_8x8.goal_cell


def test_solution_steps_are_adjacent(grid_8x8):
    """Consecutive cells in the solution must be orthogonally adjacent."""
    for (r0, c0), (r1, c1) in zip(
        grid_8x8.solution_cells[:-1],
        grid_8x8.solution_cells[1:]
    ):
        dist = abs(r1 - r0) + abs(c1 - c0)
        assert dist == 1, f"Non-adjacent step ({r0},{c0}) → ({r1},{c1})"


def test_solution_does_not_pass_through_walls(grid_8x8):
    """Every step in the solution must pass through an open wall slot."""
    sol = grid_8x8.solution_cells
    for (r0, c0), (r1, c1) in zip(sol[:-1], sol[1:]):
        wr = r0 + r1 + 1
        wc = c0 + c1 + 1
        assert not grid_8x8.wall_map[wr][wc], (
            f"Solution passes through solid wall at map[{wr}][{wc}]"
        )


def test_optimal_path_length(grid_8x8):
    """Path length = (steps) × pitch (all moves are unit steps)."""
    expected = (len(grid_8x8.solution_cells) - 1) * grid_8x8.pitch
    assert abs(grid_8x8.optimal_path_length_m() - expected) < 1e-9


# ── 4. G1 physical fit ────────────────────────────────────────────────────────

def test_corridor_fits_g1_default():
    """Default corridor (1.2 m) provides ≥ G1_BODY_WIDTH clearance."""
    g = MazeGrid(seed=1, grid_size=8, corridor_width=1.2)
    assert g.corridor_width >= G1_BODY_WIDTH_M * 2, (
        f"Corridor {g.corridor_width:.2f} m < min {G1_BODY_WIDTH_M*2:.2f} m"
    )


def test_corridor_min_rejected():
    """corridor_width < MIN_CORRIDOR_M must raise ValueError."""
    with pytest.raises(ValueError, match="too narrow"):
        MazeGrid(seed=1, grid_size=8, corridor_width=0.3)


def test_all_difficulty_presets_fit_g1():
    """Every difficulty preset satisfies the G1 physical fit constraint."""
    for name, params in DIFFICULTY_PRESETS.items():
        cw = params["corridor_width"]
        assert cw >= MIN_CORRIDOR_M, (
            f"Preset '{name}' corridor {cw:.2f} m < min {MIN_CORRIDOR_M:.2f} m"
        )


# ── 5. World-coordinate sanity ────────────────────────────────────────────────

def test_start_at_world_origin(grid_8x8):
    """Start cell (0,0) must map to world origin (0.0, 0.0)."""
    x, y = grid_8x8.cell_centre_world(0, 0)
    assert abs(x) < 1e-9 and abs(y) < 1e-9, f"Start not at origin: ({x:.6f}, {y:.6f})"


def test_goal_at_correct_offset(grid_8x8):
    """Goal cell (N-1, N-1) must be at ((N-1)*pitch, (N-1)*pitch)."""
    N = grid_8x8.N
    P = grid_8x8.pitch
    gx, gy = grid_8x8.cell_centre_world(N-1, N-1)
    expected = (N - 1) * P
    assert abs(gx - expected) < 1e-9, f"Goal x: {gx:.4f} ≠ {expected:.4f}"
    assert abs(gy - expected) < 1e-9, f"Goal y: {gy:.4f} ≠ {expected:.4f}"


def test_solution_world_xy_length(grid_8x8):
    """solution_world_xy must have same length as solution_cells."""
    assert len(grid_8x8.solution_world_xy()) == len(grid_8x8.solution_cells)


def test_solution_dict_schema():
    """to_solution_dict must contain all required keys with correct types."""
    g   = MazeGrid(seed=7, grid_size=6)
    sol = g.to_solution_dict()

    required_keys = [
        "seed", "grid_size", "corridor_width_m", "wall_thickness_m",
        "wall_height_m", "cell_pitch_m",
        "start_cell", "goal_cell",
        "start_world_xy_m", "goal_world_xy_m",
        "solution_cells", "solution_world_xy_m",
        "optimal_path_length_m", "n_solution_steps", "maze_footprint_m",
        "g1_body_width_m", "clearance_each_side_m",
    ]
    for key in required_keys:
        assert key in sol, f"Missing key: {key}"

    # JSON round-trip
    rt = json.loads(json.dumps(sol))
    assert rt["seed"] == 7
    assert rt["grid_size"] == 6


# ── 6. MuJoCo compilation ─────────────────────────────────────────────────────

@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_scene_compiles_in_mujoco():
    """MazeScene.build() must produce a valid MjModel without errors."""
    import mujoco
    grid  = MazeGrid(seed=42, grid_size=6)
    scene = MazeScene(grid, G1_SCENE)
    model, spec = scene.build()

    assert model.nq > 0,   "Compiled model has no DOFs"
    assert model.nbody > 0, "Compiled model has no bodies"

    # Confirm maze wall geoms exist in the compiled model
    wall_names = []
    for i in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i)
        if name and name.startswith(("wall_", "corner_", "hwall_", "vwall_")):
            wall_names.append(name)
    assert len(wall_names) > 0, "No maze wall geoms found in compiled model"


@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_scene_100_steps_stable():
    """100 sim steps with maze walls must produce no NaN/Inf in qpos."""
    import mujoco
    import numpy as np
    grid  = MazeGrid(seed=42, grid_size=6)
    scene = MazeScene(grid, G1_SCENE)
    model, _ = scene.build()
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert np.isfinite(data.qpos).all(), "qpos has NaN/Inf after 100 steps with maze"


@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_start_goal_sites_in_model():
    """'start' and 'goal' sites must exist in the compiled model."""
    import mujoco
    grid  = MazeGrid(seed=42, grid_size=6)
    scene = MazeScene(grid, G1_SCENE)
    model, _ = scene.build()
    for site_name in ("start", "goal"):
        sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site_name)
        assert sid >= 0, f"Site '{site_name}' not found in compiled model"


# ── 7. Grid-size sweep ────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [4, 6, 10, 15])
def test_various_grid_sizes(n):
    """Generator must work for a range of grid sizes."""
    g = MazeGrid(seed=99, grid_size=n)
    assert len(g.solution_cells) >= 2
    assert g.solution_cells[0]  == (0, 0)
    assert g.solution_cells[-1] == (n-1, n-1)


# ── 8. Full generate() pipeline ──────────────────────────────────────────────

@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_generate_writes_expected_files(tmp_path):
    """generate() must write solution.json, maze_scene.xml, maze_viz.png."""
    grid, out = generate(seed=42, grid_size=6, out_dir=tmp_path, quiet=True)

    assert (tmp_path / "solution.json").exists()
    assert (tmp_path / "maze_scene.xml").exists()
    assert (tmp_path / "maze_viz.png").exists()

    sol = json.loads((tmp_path / "solution.json").read_text())
    assert sol["seed"] == 42
    assert sol["grid_size"] == 6


@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_generate_determinism_via_files(tmp_path):
    """Running generate() twice with the same seed must produce identical solution.json."""
    d1 = tmp_path / "run1"
    d2 = tmp_path / "run2"
    generate(seed=1337, grid_size=6, out_dir=d1, visualize=False, quiet=True)
    generate(seed=1337, grid_size=6, out_dir=d2, visualize=False, quiet=True)
    s1 = json.loads((d1 / "solution.json").read_text())
    s2 = json.loads((d2 / "solution.json").read_text())
    assert s1 == s2, "Same seed produced different solution.json"
