"""
Phase 2 test suite — maze/generator.py
=======================================
Covers every requirement from the assignment spec:

  REQ-1  Same seed  -> byte-identical XML output (determinism)
  REQ-2  New seed   -> completely different layout
  REQ-3  Corridors physically fit the G1 footprint
  REQ-4  BFS ground-truth solution is valid
  REQ-5  MuJoCo compiles the scene without errors
  REQ-6  Difficulty presets produce correct parameters
  REQ-7  solution.json schema is complete and JSON-round-trips cleanly
  REQ-8  Wall-map structural invariants (corners solid, cell centres open, boundary solid)
  REQ-9  Perfect-maze property (every cell reachable)
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from maze.generator import (
    G1_BODY_WIDTH_M,
    DIFFICULTY_PRESETS,
    MIN_CORRIDOR_M,
    MazeGrid,
    MazeScene,
    generate,
)

G1_SCENE = ROOT / "robot" / "model" / "g1" / "scene.xml"


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def grid42():
    return MazeGrid(seed=42, grid_size=8)


# ═════════════════════════════════════════════════════════════════════════════
# REQ-1  Determinism — same seed => byte-identical XML
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_same_seed_xml_is_byte_identical(tmp_path):
    """
    Running generate() twice with the same seed must produce
    100% byte-identical maze_scene.xml files.
    """
    run_a = tmp_path / "a"
    run_b = tmp_path / "b"

    generate(seed=42, grid_size=8, out_dir=run_a, visualize=False, quiet=True)
    generate(seed=42, grid_size=8, out_dir=run_b, visualize=False, quiet=True)

    xml_a = (run_a / "maze_scene.xml").read_bytes()
    xml_b = (run_b / "maze_scene.xml").read_bytes()

    assert xml_a == xml_b, (
        f"Same seed produced different XML files.\n"
        f"  Run A: {len(xml_a)} bytes\n"
        f"  Run B: {len(xml_b)} bytes\n"
        f"  First difference at byte: "
        f"{next(i for i,(a,b) in enumerate(zip(xml_a,xml_b)) if a!=b)}"
        if xml_a != xml_b else ""
    )


@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_same_seed_solution_json_identical(tmp_path):
    """solution.json must also be byte-identical across runs of the same seed."""
    run_a = tmp_path / "a"
    run_b = tmp_path / "b"

    generate(seed=1337, grid_size=10, out_dir=run_a, visualize=False, quiet=True)
    generate(seed=1337, grid_size=10, out_dir=run_b, visualize=False, quiet=True)

    assert (run_a / "solution.json").read_text(encoding="utf-8") == \
           (run_b / "solution.json").read_text(encoding="utf-8")


def test_same_seed_wall_map_identical():
    """Wall map (the ground truth) must be identical for the same seed."""
    g1 = MazeGrid(seed=42, grid_size=8)
    g2 = MazeGrid(seed=42, grid_size=8)
    assert g1.wall_map == g2.wall_map


def test_same_seed_solution_path_identical():
    """Solution cell path must be identical for the same seed."""
    g1 = MazeGrid(seed=42, grid_size=8)
    g2 = MazeGrid(seed=42, grid_size=8)
    assert g1.solution_cells == g2.solution_cells


# ═════════════════════════════════════════════════════════════════════════════
# REQ-2  Different seed => completely different layout
# ═════════════════════════════════════════════════════════════════════════════

def test_different_seeds_produce_different_wall_maps():
    """
    Every pair of seeds in the test set must produce a unique wall map.
    (Collision probability is astronomically low for a perfect maze.)
    """
    seeds = [1, 2, 3, 42, 100, 999, 12345]
    maps  = {s: str(MazeGrid(seed=s, grid_size=8).wall_map) for s in seeds}
    unique = set(maps.values())
    assert len(unique) == len(seeds), (
        f"Seed collision detected — {len(seeds) - len(unique)} duplicate(s)"
    )


@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_different_seeds_xml_files_differ(tmp_path):
    """XML files for different seeds must NOT be byte-identical."""
    d1 = tmp_path / "s1"
    d2 = tmp_path / "s2"

    generate(seed=10, grid_size=8, out_dir=d1, visualize=False, quiet=True)
    generate(seed=20, grid_size=8, out_dir=d2, visualize=False, quiet=True)

    xml_10 = (d1 / "maze_scene.xml").read_bytes()
    xml_20 = (d2 / "maze_scene.xml").read_bytes()

    assert xml_10 != xml_20, "Different seeds produced identical XML — generator is broken"


def test_different_seeds_solution_paths_differ():
    """Solution paths for different seeds must differ."""
    paths = [MazeGrid(seed=s, grid_size=8).solution_cells for s in range(5)]
    unique = {str(p) for p in paths}
    assert len(unique) == 5, "Different seeds produced identical solution paths"


# ═════════════════════════════════════════════════════════════════════════════
# REQ-3  G1 physical fit
# ═════════════════════════════════════════════════════════════════════════════

def test_default_corridor_fits_g1():
    g = MazeGrid(seed=1, grid_size=8)
    assert g.corridor_width >= MIN_CORRIDOR_M

def test_all_difficulty_presets_fit_g1():
    for name, p in DIFFICULTY_PRESETS.items():
        assert p["corridor_width"] >= MIN_CORRIDOR_M, f"Preset '{name}' too narrow"

def test_corridor_too_narrow_raises():
    with pytest.raises(ValueError, match="too narrow"):
        MazeGrid(seed=1, grid_size=8, corridor_width=0.3)

def test_clearance_both_sides_positive():
    g = MazeGrid(seed=1, grid_size=8, corridor_width=1.2)
    clearance = (g.corridor_width - G1_BODY_WIDTH_M) / 2
    assert clearance > 0, f"No clearance: {clearance:.3f} m"


# ═════════════════════════════════════════════════════════════════════════════
# REQ-4  BFS solution validity
# ═════════════════════════════════════════════════════════════════════════════

def test_solution_exists(grid42):
    assert len(grid42.solution_cells) >= 2

def test_solution_start_end(grid42):
    assert grid42.solution_cells[0]  == grid42.start_cell
    assert grid42.solution_cells[-1] == grid42.goal_cell

def test_solution_all_steps_adjacent(grid42):
    for (r0,c0),(r1,c1) in zip(grid42.solution_cells, grid42.solution_cells[1:]):
        assert abs(r1-r0) + abs(c1-c0) == 1, f"Non-adjacent step ({r0},{c0})->({r1},{c1})"

def test_solution_no_wall_crossings(grid42):
    for (r0,c0),(r1,c1) in zip(grid42.solution_cells, grid42.solution_cells[1:]):
        assert not grid42.wall_map[r0+r1+1][c0+c1+1], "Solution crosses a solid wall"

def test_solution_world_xy_matches_cells(grid42):
    for (r,c),(wx,wy) in zip(grid42.solution_cells, grid42.solution_world_xy()):
        ex, ey = grid42.cell_centre_world(r, c)
        assert abs(wx-ex) < 1e-9 and abs(wy-ey) < 1e-9

def test_optimal_path_length_formula(grid42):
    expected = (len(grid42.solution_cells) - 1) * grid42.pitch
    assert abs(grid42.optimal_path_length_m() - expected) < 1e-9


# ═════════════════════════════════════════════════════════════════════════════
# REQ-5  MuJoCo compilation
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_mujoco_compiles_clean():
    import mujoco
    grid  = MazeGrid(seed=42, grid_size=6)
    model, _ = MazeScene(grid, G1_SCENE).build()
    assert model.nq > 0 and model.nbody > 0

@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_mujoco_wall_geoms_present():
    import mujoco
    grid  = MazeGrid(seed=42, grid_size=6)
    model, _ = MazeScene(grid, G1_SCENE).build()
    walls = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i)
        for i in range(model.ngeom)
        if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) and
           mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i).startswith(
               ("corner_","hwall_","vwall_"))
    ]
    assert len(walls) > 0, "No maze wall geoms in compiled model"

@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_mujoco_start_goal_sites():
    import mujoco
    grid  = MazeGrid(seed=42, grid_size=6)
    model, _ = MazeScene(grid, G1_SCENE).build()
    for name in ("start", "goal"):
        sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, name)
        assert sid >= 0, f"Site '{name}' missing from compiled model"

@pytest.mark.skipif(not G1_SCENE.exists(), reason="G1 model not downloaded")
def test_100_sim_steps_no_nan():
    import mujoco, numpy as np
    grid  = MazeGrid(seed=42, grid_size=6)
    model, _ = MazeScene(grid, G1_SCENE).build()
    data  = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert np.isfinite(data.qpos).all(), "qpos contains NaN/Inf after 100 steps"


# ═════════════════════════════════════════════════════════════════════════════
# REQ-6  Difficulty presets
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("name,params", DIFFICULTY_PRESETS.items())
def test_difficulty_preset_values(name, params):
    g = MazeGrid(seed=1, **params)
    assert g.N              == params["grid_size"]
    assert g.corridor_width == params["corridor_width"]
    assert len(g.solution_cells) >= 2

@pytest.mark.parametrize("n", [4, 6, 10, 15, 20])
def test_grid_size_sweep(n):
    g = MazeGrid(seed=7, grid_size=n)
    assert g.solution_cells[0]  == (0, 0)
    assert g.solution_cells[-1] == (n-1, n-1)


# ═════════════════════════════════════════════════════════════════════════════
# REQ-7  solution.json schema
# ═════════════════════════════════════════════════════════════════════════════

def test_solution_dict_all_keys_present():
    sol = MazeGrid(seed=5, grid_size=6).to_solution_dict()
    required = [
        "seed","grid_size","corridor_width_m","wall_thickness_m","wall_height_m",
        "cell_pitch_m","start_cell","goal_cell","start_world_xy_m","goal_world_xy_m",
        "solution_cells","solution_world_xy_m","optimal_path_length_m",
        "n_solution_steps","maze_footprint_m","g1_body_width_m","clearance_each_side_m",
    ]
    for k in required:
        assert k in sol, f"Missing key: {k}"

def test_solution_dict_json_roundtrip():
    sol = MazeGrid(seed=5, grid_size=6).to_solution_dict()
    rt  = json.loads(json.dumps(sol))
    assert rt["seed"]      == sol["seed"]
    assert rt["grid_size"] == sol["grid_size"]
    assert rt["solution_cells"] == sol["solution_cells"]

def test_solution_dict_no_nan_inf():
    import math
    sol = MazeGrid(seed=5, grid_size=6).to_solution_dict()
    floats = [
        sol["optimal_path_length_m"],
        sol["clearance_each_side_m"],
        *sol["start_world_xy_m"],
        *sol["goal_world_xy_m"],
        *sol["maze_footprint_m"],
    ]
    for v in floats:
        assert math.isfinite(v), f"Non-finite value in solution dict: {v}"


# ═════════════════════════════════════════════════════════════════════════════
# REQ-8  Wall-map structural invariants
# ═════════════════════════════════════════════════════════════════════════════

def test_wall_map_shape(grid42):
    N = grid42.N; G = 2*N+1
    assert len(grid42.wall_map) == G
    assert all(len(r) == G for r in grid42.wall_map)

def test_cell_centres_open(grid42):
    for r in range(grid42.N):
        for c in range(grid42.N):
            assert not grid42.wall_map[2*r+1][2*c+1], f"Cell ({r},{c}) centre is solid"

def test_corners_always_solid(grid42):
    G = 2*grid42.N+1
    for gr in range(0, G, 2):
        for gc in range(0, G, 2):
            assert grid42.wall_map[gr][gc], f"Corner ({gr},{gc}) is open"

def test_outer_boundary_solid(grid42):
    G = 2*grid42.N+1
    for i in range(G):
        assert grid42.wall_map[0][i],   f"South boundary open at col {i}"
        assert grid42.wall_map[G-1][i], f"North boundary open at col {i}"
        assert grid42.wall_map[i][0],   f"West boundary open at row {i}"
        assert grid42.wall_map[i][G-1], f"East boundary open at row {i}"


# ═════════════════════════════════════════════════════════════════════════════
# REQ-9  Perfect-maze property
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("seed", [1, 42, 999])
def test_all_cells_reachable(seed):
    """BFS from (0,0) must visit every cell exactly once (perfect maze)."""
    from collections import deque
    g = MazeGrid(seed=seed, grid_size=8)
    N = g.N
    visited = {(0,0)}
    queue   = deque([(0,0)])
    while queue:
        r, c = queue.popleft()
        for nr,nc in [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]:
            if 0 <= nr < N and 0 <= nc < N and (nr,nc) not in visited:
                if not g.wall_map[r+nr+1][c+nc+1]:
                    visited.add((nr,nc)); queue.append((nr,nc))
    assert len(visited) == N*N, f"seed={seed}: {len(visited)}/{N*N} cells reachable"
