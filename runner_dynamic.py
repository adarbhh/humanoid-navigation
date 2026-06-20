"""
Dynamic runner — identical maze to runner.py (seed 42) with one addition:
a moving wall that slides back and forth across a corridor on the path.

The wall is a flat mocap box.  It oscillates perpendicular to the corridor
(side-to-side from the robot's point of view).  The robot's stop/go decision
is made by measuring the perpendicular distance from the wall's current centre
to the nearest planned-path segment:

  wall ON path  (dist < STOP_DIST)  ->  stop and wait
  wall OFF path (dist >= GO_DIST)   ->  resume on original route

No A* replanning.  The robot always resumes on its original planned route.

Usage
-----
  python runner_dynamic.py --seed 42
  python runner_dynamic.py --seed 42 --demo
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import webbrowser
from collections import deque
from pathlib import Path

try:
    import psutil as _psutil
except ImportError:
    _psutil = None

try:
    from rich.live    import Live as _RichLive
    from rich.panel   import Panel as _RichPanel
    from rich.table   import Table as _RichTable
    from rich.console import Console as _RichConsole
    _RICH = True
except ImportError:
    _RICH = False

try:
    from dashboard_server import DashboardServer as _DashboardServer
    _DASHBOARD = True
except Exception:
    _DASHBOARD = False

import mujoco
import mujoco.viewer
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from maze.generator    import MazeGrid, MazeScene, DIFFICULTY_PRESETS
from robot.sensors     import get_lidar, get_imu, get_gt_pose
from robot.walking_policy.interface import WalkingPolicyInterface
from robot.recorder    import Recorder
from navigation.occupancy_grid import OccupancyGrid
from navigation.localization   import Localizer
from navigation.planner        import plan
from navigation.controller     import PurePursuitController
from viz                       import Visualizer

G1_SCENE     = ROOT / "robot" / "model" / "g1" / "scene.xml"
DYNAMIC_HTML = ROOT / "dashboard" / "index_dynamic.html"
N_LIDAR_RAYS = 16
LIDAR_FOV    = np.deg2rad(270)
LIDAR_CUTOFF = 10.0
CONTROL_HZ   = 60
INFLATE_R    = 3

STUCK_WINDOW_TICKS = 60   # 1 s at 60 Hz
STUCK_DIST_M       = 0.05
RECOVER_DIST_M     = 0.10

# ── Moving wall parameters ────────────────────────────────────────────────────
_WALL_COLOR   = [0.2, 0.5, 0.9, 0.85]   # blue, slightly transparent
_WALL_SPEED   = 0.18     # m/s — how fast the wall slides
_INTRO_DELAY  = 10.0     # seconds wall waits at clear before first slide to blocking
_BLOCK_DWELL  = 8.0      # seconds wall stays at blocking position
_CLEAR_DWELL  = 10.0     # seconds wall stays at clear position (robot passes through)

# Stop/go thresholds: perpendicular distance from wall centre to planned path.
# Small gap prevents toggling (hysteresis).
_STOP_DIST    = 0.35     # m — wall is "blocking" when this close to path centre
_GO_DIST      = 0.55     # m — wall is "clear" when this far from path centre

# Robot only stops when it is within this distance of the wall AND wall is blocking.
# This ensures the robot walks right up to the wall before stopping.
_SAFE_STOP_DIST = 1.0    # m — stop when robot is this close to wall

# Outer gate: don't even check when robot is far away.
_ENGAGE_DIST  = 4.0      # m


# ── Helpers ───────────────────────────────────────────────────────────────────

def _smoothstep(t: float) -> float:
    """Ease-in/ease-out: starts and ends at zero velocity, peaks at t=0.5."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)



def _find_body(body, name: str):
    if body.name == name:
        return body
    for child in body.bodies:
        r = _find_body(child, name)
        if r is not None:
            return r
    return None


def _pointing_quat(theta: float) -> list:
    s = np.sin(np.pi / 4)
    return [s, -s * np.sin(theta), s * np.cos(theta), 0.0]


def _wall_to_path_dist(wx: float, wy: float, path: list) -> float:
    """Perpendicular distance from wall centre to the nearest path segment."""
    min_d = float("inf")
    for i in range(len(path) - 1):
        ax, ay = path[i]
        bx, by = path[i + 1]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1e-10:
            d = float(np.hypot(wx - ax, wy - ay))
        else:
            t = max(0.0, min(1.0, ((wx - ax) * dx + (wy - ay) * dy) / seg_sq))
            d = float(np.hypot(wx - (ax + t * dx), wy - (ay + t * dy)))
        if d < min_d:
            min_d = d
    return min_d


def _path_length(trajectory: list[tuple]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(trajectory, trajectory[1:]):
        total += np.hypot(x1 - x0, y1 - y0)
    return total


# ── Scene builder ─────────────────────────────────────────────────────────────

def build_scene(seed: int, grid_size: int):
    """Identical to runner.py build_scene, plus one sliding-wall mocap body."""
    grid  = MazeGrid(seed=seed, grid_size=grid_size)
    scene = MazeScene(grid, G1_SCENE)
    _, spec = scene.build()

    torso = _find_body(spec.worldbody, "torso_link")
    if torso is None:
        raise RuntimeError("torso_link not found")

    angles = np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR_RAYS)
    hl = 0.12
    for i, theta in enumerate(angles):
        site       = torso.add_site()
        site.name  = f"lidar_site_{i:02d}"
        site.type  = mujoco.mjtGeom.mjGEOM_SPHERE
        site.size  = [0.001, 0.001, 0.001]
        site.pos   = [hl * np.cos(theta), hl * np.sin(theta), 0.0]
        site.quat  = _pointing_quat(theta)
        site.rgba  = [0.0, 0.0, 0.0, 0.0]
        site.group = 5

    for i in range(N_LIDAR_RAYS):
        sensor         = spec.add_sensor()
        sensor.name    = f"lidar_{i:02d}"
        sensor.type    = mujoco.mjtSensor.mjSENS_RANGEFINDER
        sensor.objtype = mujoco.mjtObj.mjOBJ_SITE
        sensor.objname = f"lidar_site_{i:02d}"
        sensor.cutoff  = LIDAR_CUTOFF

    cam            = torso.add_camera()
    cam.name       = "nav_camera"
    cam.pos        = [0.16, 0.0, 0.07]
    cam.fovy       = 60.0
    cam.quat       = [0.7071, 0.0, 0.7071, 0.0]
    cam.resolution = [640, 480]

    # Moving wall: flat mocap box parked underground until positioned.
    # contype=0 so it can slide freely through maze walls.
    wall       = spec.worldbody.add_body()
    wall.name  = "moving_wall"
    wall.mocap = True
    wall.pos   = [0.0, 0.0, -10.0]

    panel           = wall.add_geom()
    panel.type      = mujoco.mjtGeom.mjGEOM_BOX
    # size [0.06, 0.75, 1.0]: 12 cm thick, 1.5 m wide (spans any corridor),
    # 2 m tall.  The long axis (0.75) is in local-Y so it faces across the corridor.
    panel.size      = [0.06, 0.75, 1.0]
    panel.pos       = [0.0, 0.0, 1.0]   # bottom flush with body origin (floor)
    panel.rgba      = _WALL_COLOR
    panel.contype   = 0
    panel.conaffinity = 0

    model = spec.compile()
    data  = mujoco.MjData(model)
    return model, data, grid


# ── Episode loop ──────────────────────────────────────────────────────────────

def run_episode(
    seed:      int,
    grid_size: int,
    max_time:  float = 300.0,
    visualize: bool  = True,
    record:    bool  = False,
    speed:     float = 2.0,
    demo:      bool  = False,
) -> dict:
    print(f"\n=== Dynamic Episode  seed={seed}  grid={grid_size}x{grid_size} ===\n")
    wall_time_start = time.perf_counter()

    model, data, maze_grid = build_scene(seed, grid_size)

    policy = WalkingPolicyInterface(model, backend="kinematic")
    mujoco.mj_resetDataKeyframe(model, data, 0)
    data.qpos[0], data.qpos[1] = 0.0, 0.0

    # Navigation grid (same as runner.py)
    occ_plan_raw = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=16.0,
                                  y_min=-1.0, y_max=16.0)
    occ_plan_raw.load_from_maze(maze_grid)
    occ_nav = occ_plan_raw.inflated(INFLATE_R)
    occ_sensor = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=16.0,
                                y_min=-1.0, y_max=16.0)

    goal_xy = maze_grid.cell_centre_world(*maze_grid.goal_cell)
    path    = [(float(x), float(y)) for x, y in maze_grid.solution_world_xy()]
    print(f"Path: {len(path)} waypoints  "
          f"optimal={maze_grid.optimal_path_length_m():.1f} m\n")

    theta0 = 0.0
    if len(path) >= 2:
        dx = path[1][0] - path[0][0]; dy = path[1][1] - path[0][1]
        theta0 = float(np.arctan2(dy, dx))
    data.qpos[3] = np.cos(theta0 / 2.0)
    data.qpos[6] = np.sin(theta0 / 2.0)
    mujoco.mj_forward(model, data)

    # ── Place the moving wall on the path ─────────────────────────────────────
    _wall_body_id  = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "moving_wall")
    _wall_mocap_id: int | None = None
    _wall_pos      = np.array([0.0, 0.0, 0.0])   # Z set once placed
    _wall_axis     = 1       # which world axis the wall slides on (0=X, 1=Y)
    _wall_block_v  = 0.0    # coordinate on that axis when blocking (path centre)
    _wall_clear_v  = 0.0    # coordinate on that axis when fully clear

    # Eased-slide state machine
    # Phases: "intro" → "dwell_clear" → "slide_to_block" → "dwell_block" → "slide_to_clear" → …
    _wall_phase      = "intro"   # current phase
    _wall_phase_end  = 0.0       # sim-time when current phase ends
    _wall_slide_from = 0.0       # axis value at slide start
    _wall_slide_to   = 0.0       # axis value at slide end
    _wall_slide_dur  = 0.0       # total duration of current slide (s)

    if _wall_body_id >= 0 and len(path) >= 6:
        _wall_mocap_id = int(model.body_mocapid[_wall_body_id])
        half_corr = maze_grid.corridor_width / 2.0

        # Find a long-enough segment on the path (skip first few near start)
        placed = False
        for _i in range(6, len(path)):
            ax, ay = path[_i - 1]; bx, by = path[_i]
            seg_len = float(np.hypot(bx - ax, by - ay))
            if seg_len < 0.8:
                continue

            # Midpoint of the segment = wall blocking position
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0

            # Corridor direction tells us which axis to slide on.
            in_x = abs(bx - ax) >= abs(by - ay)
            if in_x:
                _wall_axis    = 1
                _wall_block_v = my
                # Pick the side (+Y or -Y) that has more free space in the grid.
                cy_plus  = occ_plan_raw.world_to_cell(mx, my + half_corr + 0.6)
                cy_minus = occ_plan_raw.world_to_cell(mx, my - half_corr - 0.6)
                if occ_plan_raw.in_bounds(*cy_plus) and \
                        occ_plan_raw.grid[cy_plus] != OccupancyGrid.OCCUPIED:
                    _wall_clear_v = my + half_corr + 0.6
                else:
                    _wall_clear_v = my - half_corr - 0.6
                _wall_pos[:]  = [mx, _wall_block_v, 0.0]
            else:
                _wall_axis    = 0
                _wall_block_v = mx
                cx_plus  = occ_plan_raw.world_to_cell(mx + half_corr + 0.6, my)
                cx_minus = occ_plan_raw.world_to_cell(mx - half_corr - 0.6, my)
                if occ_plan_raw.in_bounds(*cx_plus) and \
                        occ_plan_raw.grid[cx_plus] != OccupancyGrid.OCCUPIED:
                    _wall_clear_v = mx + half_corr + 0.6
                else:
                    _wall_clear_v = mx - half_corr - 0.6
                _wall_pos[:]  = [_wall_block_v, my, 0.0]

            # Wall starts at the CLEAR position so the robot walks immediately.
            # After _INTRO_DELAY seconds it slides into the blocking position.
            _wall_pos[_wall_axis] = _wall_clear_v
            _wall_phase     = "intro"
            _wall_phase_end = _INTRO_DELAY
            placed = True
            print(f"  Moving wall: path segment [{_i-1}→{_i}]  "
                  f"axis={'Y' if in_x else 'X'}  "
                  f"block_v={_wall_block_v:.2f}  clear_v={_wall_clear_v:.2f}\n")
            break

        if placed:
            data.mocap_pos[_wall_mocap_id] = _wall_pos
            mujoco.mj_forward(model, data)
        else:
            _wall_mocap_id = None
            print("  WARNING: no suitable path segment for moving wall\n")
    else:
        print("  WARNING: moving_wall body not found — running without wall\n")

    # ── Navigation stack (identical to runner.py) ─────────────────────────────
    localizer  = Localizer(x0=0.0, y0=0.0, theta0=theta0, rng_seed=seed)
    controller = PurePursuitController(
        lookahead=0.6, max_vx=0.35, max_yaw=1.5, goal_tol=0.35
    )
    controller.set_path(path)

    lidar_angles = np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR_RAYS)
    dt_control   = 1.0 / CONTROL_HZ

    rec: Recorder | None = None
    if record:
        rec = Recorder(model, seed=seed, grid_size=grid_size, out_dir="runs")
        rec.record_meta(start_xy=(0.0, 0.0), goal_xy=goal_xy,
                        waypoints=path, occ_nav=occ_nav)

    # ── KPI tracking ──────────────────────────────────────────────────────────
    trajectory_est: list[tuple]  = [(0.0, 0.0)]
    trajectory_gt:  list[tuple]  = [(0.0, 0.0)]
    loc_err_history: list[float] = []
    lidar_min_history: list[float] = []
    yaw_rate_history:  list[float] = []
    vx_history:        list[float] = []
    n_wall_collisions = 0

    _stuck_deque: deque = deque(maxlen=STUCK_WINDOW_TICKS)
    n_stuck_events = 0
    n_recoveries   = 0
    _in_stuck      = False
    _stuck_sim_time = 0.0
    recovery_times: list[float] = []

    success    = False
    t_goal     = None
    last_yaw   = 0.0
    last_print = 0.0
    _cam_tick  = 0
    prev_tick_start_x = 0.0
    prev_tick_start_y = 0.0

    # Dynamic-obstacle nav state
    _ob_state        = "CLEAR"   # "CLEAR" or "WAITING"
    _ob_waits        = 0
    _ob_cooldown_end = 0.0       # sim-time before which no new STOP is triggered

    def _deviation_from_path(px, py):
        min_d = float("inf")
        for i in range(len(path) - 1):
            ax, ay = path[i]; bx, by = path[i + 1]
            dx, dy = bx - ax, by - ay
            sq = dx*dx + dy*dy
            if sq < 1e-10:
                d = float(np.hypot(px - ax, py - ay))
            else:
                t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / sq))
                d = float(np.hypot(px-(ax+t*dx), py-(ay+t*dy)))
            min_d = min(min_d, d)
        return min_d

    _live_stats: dict = {
        "sim_time":           0.0,
        "goal_reached":       False,
        "time_to_goal":       None,
        "n_wall_collisions":  0,
        "n_stuck_events":     0,
        "dist_to_goal":       0.0,
        "loc_err":            0.0,
        "x_est":              0.0,
        "y_est":              0.0,
        "nav_hz":             float(CONTROL_HZ),
        "cam_hz":             float(CONTROL_HZ) / 2.0,
        "speed":              speed,
        "waypoints_done":     0,
        "n_waypoints":        len(path),
        "path_eff_live":      1.0,
        "path_deviation":     0.0,
        "min_wall_clearance": 9.9,
        "heading_rms":        0.0,
        "_prev_x_gt":         None,
        "_prev_y_gt":         None,
        "_dist_traveled":     0.0,
        "gate_blocked":       False,
        "gate_waits":         0,
    }

    def _sensor_occupied(px, py):
        r, c = occ_nav.world_to_cell(px, py)
        return not occ_nav.in_bounds(r, c) or occ_nav.grid[r, c] == OccupancyGrid.OCCUPIED

    def _control_tick() -> bool:
        nonlocal last_yaw, prev_tick_start_x, prev_tick_start_y, _cam_tick
        nonlocal n_wall_collisions, n_stuck_events, n_recoveries
        nonlocal _in_stuck, _stuck_sim_time
        nonlocal _ob_state, _ob_waits, _ob_cooldown_end
        nonlocal _wall_phase, _wall_phase_end, _wall_slide_from, _wall_slide_to, _wall_slide_dur

        cur_x = float(data.qpos[0])
        cur_y = float(data.qpos[1])

        # ── 1. Slide the wall (eased) ─────────────────────────────────────────
        # State machine: intro → dwell_clear → slide_to_block → dwell_block
        #                      → slide_to_clear → dwell_clear → …
        # Positions are computed with smoothstep so the wall accelerates and
        # decelerates instead of moving at a fixed speed.
        if _wall_mocap_id is not None:
            t = data.time
            slide_dist = abs(_wall_clear_v - _wall_block_v)
            slide_dur  = slide_dist / _WALL_SPEED  # total slide time (s)

            if _wall_phase == "intro" and t >= _wall_phase_end:
                _wall_phase       = "slide_to_block"
                _wall_slide_from  = _wall_clear_v
                _wall_slide_to    = _wall_block_v
                _wall_slide_dur   = slide_dur
                _wall_phase_end   = t + slide_dur

            elif _wall_phase == "slide_to_block":
                elapsed = t - (_wall_phase_end - _wall_slide_dur)
                alpha   = _smoothstep(elapsed / max(_wall_slide_dur, 1e-6))
                _wall_pos[_wall_axis] = (_wall_slide_from
                                         + (_wall_slide_to - _wall_slide_from) * alpha)
                if t >= _wall_phase_end:
                    _wall_pos[_wall_axis] = _wall_block_v
                    _wall_phase           = "dwell_block"
                    _wall_phase_end       = t + _BLOCK_DWELL

            elif _wall_phase == "dwell_block" and t >= _wall_phase_end:
                _wall_phase      = "slide_to_clear"
                _wall_slide_from = _wall_block_v
                _wall_slide_to   = _wall_clear_v
                _wall_slide_dur  = slide_dur
                _wall_phase_end  = t + slide_dur

            elif _wall_phase == "slide_to_clear":
                elapsed = t - (_wall_phase_end - _wall_slide_dur)
                alpha   = _smoothstep(elapsed / max(_wall_slide_dur, 1e-6))
                _wall_pos[_wall_axis] = (_wall_slide_from
                                         + (_wall_slide_to - _wall_slide_from) * alpha)
                if t >= _wall_phase_end:
                    _wall_pos[_wall_axis] = _wall_clear_v
                    _wall_phase           = "dwell_clear"
                    _wall_phase_end       = t + _CLEAR_DWELL

            elif _wall_phase == "dwell_clear" and t >= _wall_phase_end:
                _wall_phase      = "slide_to_block"
                _wall_slide_from = _wall_clear_v
                _wall_slide_to   = _wall_block_v
                _wall_slide_dur  = slide_dur
                _wall_phase_end  = t + slide_dur

            data.mocap_pos[_wall_mocap_id] = _wall_pos

        # ── 2. LiDAR + IMU + localisation (identical to runner.py) ───────────
        lidar  = get_lidar(model, data, prefix="lidar_")
        imu    = get_imu(model, data)
        gyro_z = float(imu["gyro"][2])

        theta_prev = localizer.theta
        cos_t = np.cos(theta_prev); sin_t = np.sin(theta_prev)
        dx_pos = cur_x - prev_tick_start_x
        dy_pos = cur_y - prev_tick_start_y
        actual_vx =  (dx_pos * cos_t + dy_pos * sin_t) / dt_control
        actual_vy = (-dx_pos * sin_t + dy_pos * cos_t) / dt_control
        localizer.update(actual_vx, actual_vy, last_yaw, gyro_z, dt_control)
        x_est, y_est, theta_est = localizer.pose

        occ_sensor.update_from_lidar(
            x_est, y_est, theta_est,
            lidar["ranges"], lidar_angles,
            min_range=0.15, max_range=LIDAR_CUTOFF - 0.1,
        )

        # ── 3. Pure-pursuit controller (identical to runner.py) ───────────────
        vx, vy, yaw_rate = controller.step(
            x_est, y_est, theta_est,
            lidar_ranges=lidar["ranges"],
            lidar_angles=lidar_angles,
        )
        # LiDAR-based wall reactions: forward slowdown + corridor centering.
        # Treats the moving wall exactly like any static wall — robot steers
        # away and maintains standard clearance as it passes.
        _pivoting = abs(yaw_rate) > 0.8
        vx, yaw_rate = controller._wall_react(
            vx, yaw_rate, lidar["ranges"], lidar_angles, _pivoting
        )

        # ── 4. Moving-wall stop/go ────────────────────────────────────────────
        # Only active when robot is within _ENGAGE_DIST of the wall centre.
        # Decision is purely geometric: how far is the wall from the planned path?
        #   small distance → wall is on/near the path → STOP
        #   large distance → wall has slid aside      → GO
        if _wall_mocap_id is not None:
            robot_to_wall = float(
                np.hypot(x_est - _wall_pos[0], y_est - _wall_pos[1])
            )
            if robot_to_wall < _ENGAGE_DIST:
                wall_d = _wall_to_path_dist(
                    float(_wall_pos[0]), float(_wall_pos[1]), path
                )
                if (_ob_state == "CLEAR"
                        and wall_d < _STOP_DIST
                        and robot_to_wall < _SAFE_STOP_DIST
                        and data.time >= _ob_cooldown_end):
                    _ob_state  = "WAITING"
                    _ob_waits += 1
                    print(f"  [STOP] t={data.time:.1f}s  "
                          f"wall on path (wall_d={wall_d:.2f}m, "
                          f"robot_dist={robot_to_wall:.2f}m)")
                elif _ob_state == "WAITING" and wall_d >= _GO_DIST:
                    _ob_state        = "CLEAR"
                    _ob_cooldown_end = data.time + _BLOCK_DWELL + _CLEAR_DWELL
                    # Clear the stuck deque so stale stationary positions don't
                    # trigger a false stuck event the moment the robot resumes.
                    _stuck_deque.clear()
                    print(f"  [GO]   t={data.time:.1f}s  "
                          f"wall cleared (d={wall_d:.2f}m)")

            elif _ob_state == "WAITING":
                # Wall moved far from robot — always resume
                _ob_state = "CLEAR"
                _stuck_deque.clear()

            if _ob_state == "WAITING":
                vx = 0.0; vy = 0.0
                # Turn to face the wall while stopped.
                angle_to_wall = math.atan2(
                    _wall_pos[1] - y_est, _wall_pos[0] - x_est
                )
                heading_err = (angle_to_wall - theta_est + math.pi) % (2 * math.pi) - math.pi
                if abs(heading_err) > 0.05:
                    yaw_rate = float(np.clip(heading_err * 2.0, -0.8, 0.8))
                else:
                    yaw_rate = 0.0

            _live_stats["gate_blocked"] = (_ob_state == "WAITING")
            _live_stats["gate_waits"]   = _ob_waits
            if _wall_mocap_id is not None:
                _live_stats["_wall_x"]    = float(_wall_pos[0])
                _live_stats["_wall_y"]    = float(_wall_pos[1])
                _live_stats["_wall_axis"] = int(_wall_axis)
                _live_stats["_wall_hw"]   = 0.75

        # ── 5. Execute motion (identical to runner.py) ────────────────────────
        policy.set_command(vx, vy, yaw_rate)
        policy.step(model, data, dt=dt_control)

        nx, ny = float(data.qpos[0]), float(data.qpos[1])
        if _sensor_occupied(nx, ny):
            n_wall_collisions += 1
            if not _sensor_occupied(nx, cur_y):
                data.qpos[1] = cur_y
            elif not _sensor_occupied(cur_x, ny):
                data.qpos[0] = cur_x
            else:
                data.qpos[0] = cur_x; data.qpos[1] = cur_y
            mujoco.mj_forward(model, data)

        # Snap-back from moving wall — axis-aware so it only fires when the robot
        # is in front of the wall face, not when the wall has slid to clear.
        # _wall_axis: the axis the wall slides on (wall face is perpendicular to this).
        # _fwd_axis:  the axis the wall faces along (corridor travel direction).
        if _wall_mocap_id is not None:
            _fwd_axis  = 1 - _wall_axis
            _fwd_dist  = abs(float(data.qpos[_fwd_axis])  - _wall_pos[_fwd_axis])
            _side_dist = abs(float(data.qpos[_wall_axis]) - _wall_pos[_wall_axis])
            # Only snap back when within wall face (0.25 m forward) AND wall width (0.8 m side).
            # When wall is at clear, _side_dist ≈ half_corr + 0.6 > 0.8 → no false trigger.
            if _fwd_dist < 0.25 and _side_dist < 0.8:
                data.qpos[0] = cur_x; data.qpos[1] = cur_y
                mujoco.mj_forward(model, data)

        prev_tick_start_x = cur_x
        prev_tick_start_y = cur_y
        last_yaw = yaw_rate

        # ── 6. KPI measurements (identical to runner.py) ──────────────────────
        trajectory_est.append((x_est, y_est))
        gt = get_gt_pose(model, data)
        trajectory_gt.append((float(gt["pos"][0]), float(gt["pos"][1])))
        loc_err_history.append(
            float(np.hypot(x_est - gt["pos"][0], y_est - gt["pos"][1]))
        )

        raw   = lidar["ranges"]
        valid = raw[(raw > 0.15) & (raw < LIDAR_CUTOFF - 0.1)]
        if valid.size and _ob_state != "WAITING":
            lidar_min_history.append(float(valid.min()))

        yaw_rate_history.append(yaw_rate)
        vx_history.append(vx)

        _stuck_deque.append((float(data.qpos[0]), float(data.qpos[1])))
        if len(_stuck_deque) == STUCK_WINDOW_TICKS and _ob_state != "WAITING":
            x0s, y0s = _stuck_deque[0]; x1s, y1s = _stuck_deque[-1]
            disp = float(np.hypot(x1s - x0s, y1s - y0s))
            if not _in_stuck and disp < STUCK_DIST_M:
                n_stuck_events += 1; _in_stuck = True; _stuck_sim_time = data.time
            elif _in_stuck and disp > RECOVER_DIST_M:
                n_recoveries += 1; recovery_times.append(data.time - _stuck_sim_time)
                _in_stuck = False

        _n = len(loc_err_history)
        _live_stats["sim_time"]          = data.time
        _live_stats["n_wall_collisions"] = n_wall_collisions
        _live_stats["n_stuck_events"]    = n_stuck_events
        _live_stats["x_est"]             = x_est
        _live_stats["y_est"]             = y_est
        _live_stats["loc_err"]           = loc_err_history[-1] if loc_err_history else 0.0
        _live_stats["ate_rmse"]          = (
            float(np.sqrt(np.mean(np.array(loc_err_history)**2)))
            if loc_err_history else 0.0)
        _live_stats["nav_hz"]            = _n / max(data.time, 0.001)
        _live_stats["cam_hz"]            = (_n // 2) / max(data.time, 0.001)
        gx, gy = goal_xy
        _live_stats["dist_to_goal"]   = float(np.hypot(x_est - gx, y_est - gy))
        _live_stats["waypoints_done"] = controller._wp_idx
        _live_stats["path_deviation"] = _deviation_from_path(x_est, y_est)
        if lidar_min_history:
            _live_stats["min_wall_clearance"] = float(min(lidar_min_history))
        if yaw_rate_history:
            _yr = np.array(yaw_rate_history[-100:])
            _live_stats["heading_rms"] = float(np.sqrt(np.mean(_yr**2)))
        _gt_x, _gt_y = float(data.qpos[0]), float(data.qpos[1])
        _px, _py = _live_stats["_prev_x_gt"], _live_stats["_prev_y_gt"]
        if _px is not None:
            _live_stats["_dist_traveled"] += float(np.hypot(_gt_x - _px, _gt_y - _py))
        _live_stats["_prev_x_gt"] = _gt_x
        _live_stats["_prev_y_gt"] = _gt_y
        _opt = maze_grid.optimal_path_length_m()
        if _opt > 0 and _live_stats["_dist_traveled"] > 0:
            _live_stats["path_eff_live"] = _live_stats["_dist_traveled"] / _opt

        goal_hit = np.hypot(x_est - gx, y_est - gy) < controller.goal_tol
        if goal_hit and not _live_stats["goal_reached"]:
            _live_stats["goal_reached"] = True
            _live_stats["time_to_goal"] = data.time

        if rec is not None:
            t = data.time
            rec.record_imu(t, imu["gyro"], imu["accel"])
            rec.record_base(t, x_est, y_est, theta_est, vx, vy, yaw_rate)
            rec.record_joints(t, data.qpos, data.qvel)
            rec.record_lidar(t, lidar["ranges"])
            rec.record_gt(t, gt["pos"], gt["quat"])
            _cam_tick += 1
            if _cam_tick % 2 == 0:
                rec.record_camera(t, data)

        return np.hypot(x_est - gx, y_est - gy) < controller.goal_tol

    # ── Run ───────────────────────────────────────────────────────────────────
    if visualize:
        _run_with_viewer(model, data, maze_grid, localizer, occ_nav, path,
                         goal_xy, _control_tick, max_time, dt_control, speed,
                         demo=demo, live_stats=_live_stats,
                         seed=seed, grid_size=grid_size,
                         trajectory_gt=trajectory_gt)
        success = True
    else:
        while data.time < max_time:
            if _control_tick():
                success = True; t_goal = data.time; break
            if data.time - last_print >= 5.0:
                last_print = data.time
                x_e, y_e, _ = localizer.pose
                gt = get_gt_pose(model, data)
                gx, gy = goal_xy
                print(f"  t={data.time:6.1f}s  "
                      f"est=({x_e:.2f},{y_e:.2f})  "
                      f"dist={np.hypot(x_e-gx, y_e-gy):.2f}m  "
                      f"wall_state={_ob_state}  waits={_ob_waits}")

    wall_time_elapsed = time.perf_counter() - wall_time_start
    capture_rates: dict[str, float] = {}
    if rec is not None:
        capture_rates = rec.close()

    # ── KPIs (identical to runner.py) ─────────────────────────────────────────
    actual_len = _path_length(trajectory_gt)
    opt_len    = maze_grid.optimal_path_length_m()
    efficiency = actual_len / opt_len if opt_len > 0 else 0.0

    _live_dist = _live_stats["_dist_traveled"]
    print(f"\n[DEBUG path_eff] live={_live_dist:.2f}m  gt={actual_len:.2f}m  "
          f"opt={opt_len:.2f}m  ratio={efficiency:.4f}x")

    gt_final = get_gt_pose(model, data)
    x_e, y_e, _ = localizer.pose
    final_loc_err     = float(np.hypot(x_e - gt_final["pos"][0], y_e - gt_final["pos"][1]))
    final_goal_err_m  = float(np.hypot(gt_final["pos"][0] - goal_xy[0],
                                       gt_final["pos"][1] - goal_xy[1]))
    loc_arr  = np.array(loc_err_history) if loc_err_history else np.array([0.0])
    ate_rmse = float(np.sqrt(np.mean(loc_arr**2)))
    drift_pct = (ate_rmse / actual_len * 100.0) if actual_len > 0 else 0.0

    min_clearance_m  = float(np.min(lidar_min_history))  if lidar_min_history else None
    mean_clearance_m = float(np.mean(lidar_min_history)) if lidar_min_history else None
    heading_rate_rms = (float(np.sqrt(np.mean(np.array(yaw_rate_history)**2)))
                        if yaw_rate_history else None)
    jerk_rms = (float(np.sqrt(np.mean(np.diff(vx_history)**2 / dt_control**2)))
                if len(vx_history) > 1 else None)

    free_cells_gt   = int(np.sum(occ_plan_raw.grid == OccupancyGrid.FREE))
    explored_cells  = int(np.sum(occ_sensor.grid != OccupancyGrid.UNKNOWN))
    map_coverage    = 100.0 * explored_cells / max(free_cells_gt, 1)
    real_time_factor = data.time / max(wall_time_elapsed, 0.001)

    nav_failures  = n_stuck_events + (0 if success else 1)
    mtbf_m        = actual_len / nav_failures if nav_failures > 0 else actual_len
    recovery_rate = (100.0 * n_recoveries / n_stuck_events
                     if n_stuck_events > 0 else 100.0)
    mean_recovery = float(np.mean(recovery_times)) if recovery_times else None

    if success:                           failure_reason = "none"
    elif n_stuck_events > 0:              failure_reason = "stuck"
    elif n_wall_collisions > 10:          failure_reason = "wall_collision"
    else:                                 failure_reason = "timeout"

    n_ticks = len(loc_err_history)
    _nav_hz = round(n_ticks / max(data.time, 0.001), 2)
    _cam_hz = round((n_ticks // 2) / max(data.time, 0.001), 2)
    _TARGETS = {"imu": 20, "base_state": 20, "joint_state": 20,
                "lidar": 20, "camera": 10, "gt_pose": 20}
    achieved_fps = ({s: round(capture_rates.get(s, 0.0), 2) for s in _TARGETS}
                    if capture_rates else
                    {"imu": _nav_hz, "base_state": _nav_hz, "joint_state": _nav_hz,
                     "lidar": _nav_hz, "camera": _cam_hz, "gt_pose": _nav_hz})
    frame_drop_pct = {s: round(max(0.0, 100.0*(1.0 - achieved_fps[s]/t)), 2)
                      for s, t in _TARGETS.items()}

    _pre_kpi = {"efficiency": efficiency, "final_goal_error_m": final_goal_err_m,
                "ate_rmse": ate_rmse, "drift_pct": drift_pct,
                "real_time_factor": real_time_factor, "mtbf_m": mtbf_m,
                "heading_rate_rms": heading_rate_rms or 0.0,
                "jerk_rms": jerk_rms or 0.0}
    n_nan_inf    = sum(1 for v in _pre_kpi.values()
                       if isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
    schema_valid = (n_nan_inf == 0)
    peak_ram_mb  = None
    if _psutil is not None:
        try: peak_ram_mb = round(_psutil.Process().memory_info().rss / 1_048_576, 1)
        except Exception: pass

    kpis = {
        "seed": seed, "grid_size": grid_size, "success": success,
        "sim_time_s": round(data.time, 2),
        "time_to_goal_s": round(t_goal, 2) if t_goal else None,
        "actual_path_m": round(actual_len, 3),
        "optimal_path_m": round(opt_len, 3),
        "path_efficiency": round(efficiency, 4),
        "final_goal_error_m": round(final_goal_err_m, 3),
        "n_wall_collisions": n_wall_collisions,
        "min_wall_clearance_m": round(min_clearance_m, 3) if min_clearance_m else None,
        "mean_wall_clearance_m": round(mean_clearance_m, 3) if mean_clearance_m else None,
        "n_stuck_events": n_stuck_events, "n_recoveries": n_recoveries,
        "recovery_rate_pct": round(recovery_rate, 1),
        "mean_recovery_s": round(mean_recovery, 2) if mean_recovery else None,
        "heading_rate_rms": round(heading_rate_rms, 4) if heading_rate_rms else None,
        "jerk_rms_m_s2": round(jerk_rms, 4) if jerk_rms else None,
        "obstacle_waits": _ob_waits,
        "final_loc_err_m": round(final_loc_err, 3),
        "mean_loc_err_m": round(float(loc_arr.mean()), 3),
        "max_loc_err_m": round(float(loc_arr.max()), 3),
        "ate_rmse_m": round(ate_rmse, 3), "drift_pct": round(drift_pct, 2),
        "map_coverage_pct": round(map_coverage, 1),
        "achieved_fps": achieved_fps, "frame_drop_pct": frame_drop_pct,
        "inter_sensor_sync_ms": 0.0, "max_sync_skew_ms": 0.0,
        "schema_valid": schema_valid, "n_nan_inf": n_nan_inf,
        "failure_reason": failure_reason, "mtbf_m": round(mtbf_m, 2),
        "n_ticks": n_ticks, "real_time_factor": round(real_time_factor, 2),
        "wall_time_s": round(wall_time_elapsed, 2), "peak_ram_mb": peak_ram_mb,
    }
    print("\n=== KPIs ===")
    for k, v in kpis.items():
        print(f"  {k:<26}: {v}")
    return kpis


# ── Rich terminal panel ───────────────────────────────────────────────────────

def _make_rich_panel(ls: dict, seed: int, grid_size: int) -> "_RichPanel":
    t = _RichTable.grid(padding=(0, 2))
    t.add_column(justify="center", min_width=26)
    t.add_column(justify="center", min_width=26)
    t.add_column(justify="center", min_width=26)

    def _val(v, fmt=".2f", unit=""):
        return "[dim]--[/dim]" if v is None else f"[bold]{v:{fmt}}[/bold]{unit}"

    goal_str = ("[bold green]YES ✓[/bold green]" if ls["goal_reached"]
                else "[bold yellow]no…[/bold yellow]")
    ttg = ls["time_to_goal"]
    ttg_str = (f"[bold green]{ttg:.1f}s[/bold green]" if ttg is not None
               else f"[bold]{ls['sim_time']:.1f}s[/bold] [dim]elapsed[/dim]")
    col1 = (f"[cyan]SOLVE[/cyan]\n"
            f"Goal reached : {goal_str}\n"
            f"Time-to-goal : {ttg_str}\n"
            f"Dist to goal : {_val(ls['dist_to_goal'], '.2f', 'm')}\n"
            f"Sim time     : {_val(ls['sim_time'], '.1f', 's')}")

    ob_str = ("[bold red]BLOCKED[/bold red]" if ls.get("gate_blocked")
              else "[bold green]clear[/bold green]")
    col2 = (f"[cyan]NAVIGATION[/cyan]\n"
            f"Collisions   : [bold red]{ls['n_wall_collisions']}[/bold red]\n"
            f"Stuck events : [bold red]{ls['n_stuck_events']}[/bold red]\n"
            f"Moving wall  : {ob_str}  (waits: {ls.get('gate_waits', 0)})\n"
            f"Loc error    : {_val(ls['loc_err'], '.3f', 'm')}")

    col3 = (f"[cyan]CAPTURE HEALTH[/cyan]\n"
            f"Nav  fps     : {_val(ls['nav_hz'], '.1f', ' Hz')}\n"
            f"Cam  fps     : {_val(ls['cam_hz'], '.1f', ' Hz')}\n"
            f"Frame drops  : [bold]0%[/bold] [dim](kinematic)[/dim]\n"
            f"Speed        : [bold]{ls.get('speed', 2.0):g}x[/bold]")

    t.add_row(col1, col2, col3)
    return _RichPanel(t,
                      title=f"[bold]G1 DYNAMIC DEMO[/bold]  "
                            f"seed=[cyan]{seed}[/cyan]  "
                            f"grid=[cyan]{grid_size}×{grid_size}[/cyan]",
                      border_style="bright_blue")


# ── Viewer loop (identical to runner.py) ─────────────────────────────────────

def _run_with_viewer(
    model, data, maze_grid, localizer, occ_nav, path, goal_xy,
    tick_fn, max_time, dt_control, speed=2.0,
    demo=False, live_stats=None, seed=0, grid_size=10,
    trajectory_gt=None,
):
    viz     = Visualizer(model, occ_nav, path, goal_xy)
    _paused = [False]

    def _key_cb(key):
        if key == 32:
            _paused[0] = not _paused[0]

    _rich_live_ctx = (
        _RichLive(_make_rich_panel(live_stats, seed, grid_size),
                  refresh_per_second=5, console=_RichConsole())
        if (demo and _RICH and live_stats is not None) else None
    )
    if _rich_live_ctx is not None:
        _rich_live_ctx.start()

    _dash_srv = None
    if demo and _DASHBOARD and live_stats is not None:
        html = DYNAMIC_HTML if DYNAMIC_HTML.exists() else None
        _dash_srv = _DashboardServer(port=7654, html_path=html)
        url = _dash_srv.start()
        print(f"\n  Dashboard: {url}  (opening browser…)\n")
        webbrowser.open(url)

    last_dash_wall = time.perf_counter()
    dash_interval  = 1.0 / 5

    with mujoco.viewer.launch_passive(model, data, key_callback=_key_cb) as viewer:
        viewer.opt.sitegroup[0] = True
        for _g in range(1, 6):
            viewer.opt.sitegroup[_g] = False
        viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_RANGEFINDER] = False

        pelvis_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        viewer.cam.type        = mujoco.mjtCamera.mjCAMERA_TRACKING
        viewer.cam.trackbodyid = pelvis_id
        viewer.cam.distance    = 6.0
        viewer.cam.elevation   = -50
        viewer.cam.azimuth     = 45

        RENDER_HZ        = 60
        render_interval  = 1.0 / RENDER_HZ
        ctrl_interval    = dt_control / max(speed, 0.1)
        viz_interval     = 1.0 / Visualizer.UPDATE_HZ
        last_ctrl_wall   = time.perf_counter()
        last_render_wall = time.perf_counter()
        last_viz_wall    = time.perf_counter()
        last_print       = 0.0

        while viewer.is_running() and data.time < max_time:
            now = time.perf_counter()

            goal_reached = False
            if not _paused[0] and now - last_ctrl_wall >= ctrl_interval:
                goal_reached = tick_fn()
                last_ctrl_wall = now

            if now - last_render_wall >= render_interval:
                viewer.sync(); last_render_wall = now

            if now - last_viz_wall >= viz_interval:
                x_e, y_e, th_e = localizer.pose
                _wi = (live_stats["_wall_x"], live_stats["_wall_y"],
                       live_stats["_wall_axis"], live_stats["_wall_hw"]) \
                      if "_wall_x" in live_stats else None
                viz.update(viewer, x_e, y_e, th_e, data.time,
                           paused=_paused[0], wall_info=_wi)
                last_viz_wall = now

            time.sleep(0.001)

            if demo and now - last_dash_wall >= dash_interval:
                if _rich_live_ctx is not None:
                    _rich_live_ctx.update(_make_rich_panel(live_stats, seed, grid_size))
                if _dash_srv is not None:
                    _dash_srv.push({
                        **{k: v for k, v in live_stats.items() if not k.startswith("_")},
                        "seed": seed, "grid_size": grid_size,
                        "minimap_b64": viz.minimap_b64,
                        "path_progress": viz._path_progress(
                            live_stats["x_est"], live_stats["y_est"]),
                    })
                last_dash_wall = now

            if not demo and data.time - last_print >= 2.0:
                last_print = data.time
                x_e, y_e, _ = localizer.pose
                gx, gy = goal_xy
                print(f"  t={data.time:6.1f}s  "
                      f"est=({x_e:.2f},{y_e:.2f})  "
                      f"dist={np.hypot(x_e-gx,y_e-gy):.2f}m")

            if goal_reached:
                if _rich_live_ctx is not None:
                    _rich_live_ctx.update(_make_rich_panel(live_stats, seed, grid_size))
                if _dash_srv is not None:
                    _gt_stride = max(1, len(trajectory_gt or []) // 800)
                    _dash_srv.push({
                        **{k: v for k, v in live_stats.items() if not k.startswith("_")},
                        "seed": seed, "grid_size": grid_size,
                        "minimap_b64": viz.minimap_b64,
                        "path_progress": viz._path_progress(
                            live_stats["x_est"], live_stats["y_est"]),
                        "planned_path": [[float(x), float(y)] for x, y in path],
                        **({"gt_trajectory": [[float(x), float(y)]
                                               for x, y in (trajectory_gt or [])[::_gt_stride]]}
                           if trajectory_gt else {}),
                    })
                viz.notify_goal(data.time)
                deadline = time.perf_counter() + 5.0
                while viewer.is_running() and time.perf_counter() < deadline:
                    t = time.perf_counter()
                    if t - last_render_wall >= render_interval:
                        viewer.sync(); last_render_wall = t
                    if t - last_viz_wall >= viz_interval:
                        x_e, y_e, th_e = localizer.pose
                        _wi = (live_stats["_wall_x"], live_stats["_wall_y"],
                               live_stats["_wall_axis"], live_stats["_wall_hw"]) \
                              if "_wall_x" in live_stats else None
                        viz.update(viewer, x_e, y_e, th_e, data.time,
                                   paused=_paused[0], wall_info=_wi)
                        last_viz_wall = t
                    if demo and t - last_dash_wall >= dash_interval:
                        if _rich_live_ctx is not None:
                            _rich_live_ctx.update(_make_rich_panel(live_stats, seed, grid_size))
                        if _dash_srv is not None:
                            _dash_srv.push({**live_stats, "seed": seed,
                                    "grid_size": grid_size,
                                    "minimap_b64": viz.minimap_b64,
                                    "path_progress": viz._path_progress(
                                        live_stats["x_est"], live_stats["y_est"])})
                        last_dash_wall = t
                    time.sleep(0.001)
                break

    if _rich_live_ctx is not None: _rich_live_ctx.stop()
    if _dash_srv is not None:      _dash_srv.stop()
    viz.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="G1 dynamic maze demo — moving wall obstacle")
    parser.add_argument("--seed",       type=int,   default=42)
    parser.add_argument("--grid-size",  type=int,   default=10)
    parser.add_argument("--max-time",   type=float, default=300.0)
    parser.add_argument("--no-viz",     action="store_true")
    parser.add_argument("--record",     action="store_true")
    parser.add_argument("--speed",      type=float, default=2.0)
    parser.add_argument("--difficulty", choices=DIFFICULTY_PRESETS.keys())
    parser.add_argument("--demo",       action="store_true")
    args = parser.parse_args()

    grid_size = args.grid_size
    if args.difficulty:
        grid_size = DIFFICULTY_PRESETS[args.difficulty]["grid_size"]

    run_episode(
        seed=args.seed,
        grid_size=grid_size,
        max_time=args.max_time,
        visualize=not args.no_viz,
        record=args.record,
        speed=args.speed,
        demo=args.demo,
    )


if __name__ == "__main__":
    main()
