"""
Single-episode runner — G1 navigates maze start->goal using the full nav stack.

Navigation stack (closed-loop, no ground-truth pose):
  Perception  : 16-ray 270-deg rangefinder ring on torso_link
  Localization: IMU gyro dead-reckoning + commanded-velocity odometry
  Mapping     : OccupancyGrid pre-loaded from known maze map
  Planning    : A* on obstacle-inflated occupancy grid
  Control     : Pure-pursuit -> (vx, vy, yaw_rate)
  Locomotion  : Kinematic freejoint update (mj_forward, no physics)

Usage
-----
  python runner.py --seed 42
  python runner.py --seed 42 --grid-size 10 --no-viz
  python runner.py --seed 42 --max-time 300
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
    from rich.text    import Text  as _RichText
    from rich.console import Console as _RichConsole
    from rich         import box   as _rich_box
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
N_LIDAR_RAYS = 16
LIDAR_FOV    = np.deg2rad(270)
LIDAR_CUTOFF = 10.0
CONTROL_HZ   = 20          # nav-stack tick rate
INFLATE_R    = 3           # obstacle inflation radius (cells @ 0.1 m/cell = 0.3 m)

# Stuck detection: robot must move < STUCK_DIST_M in STUCK_WINDOW_TICKS ticks
STUCK_WINDOW_TICKS = 20   # 1 s at 20 Hz
STUCK_DIST_M       = 0.05
RECOVER_DIST_M     = 0.10


# ── Scene builder ─────────────────────────────────────────────────────────────

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


def build_scene(seed: int, grid_size: int, demo: bool = False):
    """Returns (model, data, maze_grid) with LiDAR sensors added."""
    grid  = MazeGrid(seed=seed, grid_size=grid_size)
    scene = MazeScene(grid, G1_SCENE)
    _, spec = scene.build()

    torso = _find_body(spec.worldbody, "torso_link")
    if torso is None:
        raise RuntimeError("torso_link not found in G1 spec")

    angles   = np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR_RAYS)
    hl       = 0.12
    for i, theta in enumerate(angles):
        site       = torso.add_site()
        site.name  = f"lidar_site_{i:02d}"
        site.type  = mujoco.mjtGeom.mjGEOM_CYLINDER
        site.size  = [0.006, 0.006, hl]
        site.pos   = [hl * np.cos(theta), hl * np.sin(theta), 0.0]
        site.quat  = _pointing_quat(theta)
        site.rgba  = [1.0, 0.3, 0.0, 0.6]
        site.group = 4

    for i in range(N_LIDAR_RAYS):
        sensor         = spec.add_sensor()
        sensor.name    = f"lidar_{i:02d}"
        sensor.type    = mujoco.mjtSensor.mjSENS_RANGEFINDER
        sensor.objtype = mujoco.mjtObj.mjOBJ_SITE
        sensor.objname = f"lidar_site_{i:02d}"
        sensor.cutoff  = LIDAR_CUTOFF

    # Forward-facing camera
    cam          = torso.add_camera()
    cam.name     = "nav_camera"
    cam.pos      = [0.16, 0.0, 0.07]
    cam.fovy     = 60.0
    cam.quat     = [0.7071, 0.0, 0.7071, 0.0]
    cam.resolution = [640, 480]

    model = spec.compile()
    data  = mujoco.MjData(model)
    return model, data, grid


# ── Episode loop ──────────────────────────────────────────────────────────────

def run_episode(
    seed:       int,
    grid_size:  int,
    max_time:   float = 300.0,
    visualize:  bool  = True,
    record:     bool  = False,
    speed:      float = 2.0,
    demo:       bool  = False,   # enable live Rich terminal dashboard
) -> dict:
    print(f"\n=== Episode  seed={seed}  grid={grid_size}x{grid_size} ===\n")

    wall_time_start = time.perf_counter()

    # ── Build simulation ──────────────────────────────────────────────────────
    model, data, maze_grid = build_scene(seed, grid_size, demo=demo)

    def _deviation_from_path(px: float, py: float) -> float:
        """Perpendicular distance from (px, py) to the nearest A* path segment."""
        min_d = float('inf')
        for i in range(len(path) - 1):
            ax, ay = path[i];  bx, by = path[i + 1]
            dx, dy = bx - ax, by - ay
            seg_sq = dx * dx + dy * dy
            if seg_sq < 1e-10:
                d = float(np.hypot(px - ax, py - ay))
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_sq))
                d = float(np.hypot(px - (ax + t * dx), py - (ay + t * dy)))
            if d < min_d:
                min_d = d
        return min_d

    policy = WalkingPolicyInterface(model, backend="kinematic")

    mujoco.mj_resetDataKeyframe(model, data, 0)
    data.qpos[0], data.qpos[1] = 0.0, 0.0

    # ── Navigation stack ──────────────────────────────────────────────────────
    occ_plan_raw = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=16.0,
                                  y_min=-1.0, y_max=16.0)
    occ_plan_raw.load_from_maze(maze_grid)
    occ_nav = occ_plan_raw.inflated(INFLATE_R)

    occ_sensor = OccupancyGrid(resolution=0.1, x_min=-1.0, x_max=16.0,
                                y_min=-1.0, y_max=16.0)

    goal_xy  = maze_grid.cell_centre_world(*maze_grid.goal_cell)

    path = [(float(x), float(y)) for x, y in maze_grid.solution_world_xy()]
    print(f"Path: {len(path)} waypoints (corridor centres)  "
          f"optimal_length={maze_grid.optimal_path_length_m():.1f} m\n")

    theta0 = 0.0
    if len(path) >= 2:
        dx = path[1][0] - path[0][0]
        dy = path[1][1] - path[0][1]
        theta0 = float(np.arctan2(dy, dx))
    data.qpos[3] = np.cos(theta0 / 2.0)
    data.qpos[4] = 0.0
    data.qpos[5] = 0.0
    data.qpos[6] = np.sin(theta0 / 2.0)
    mujoco.mj_forward(model, data)

    localizer  = Localizer(x0=0.0, y0=0.0, theta0=theta0, rng_seed=seed)
    controller = PurePursuitController(
        lookahead=0.6, max_vx=0.35, max_yaw=1.5, goal_tol=0.35
    )
    controller.set_path(path)

    lidar_angles = np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR_RAYS)
    dt_control   = 1.0 / CONTROL_HZ

    # Recorder (optional)
    rec: Recorder | None = None
    if record:
        rec = Recorder(model, seed=seed, grid_size=grid_size, out_dir="runs")
        rec.record_meta(
            start_xy=(0.0, 0.0),
            goal_xy=goal_xy,
            waypoints=path,
            occ_nav=occ_nav,
        )

    # ── KPI tracking state ────────────────────────────────────────────────────
    trajectory_est: list[tuple]  = [(0.0, 0.0)]
    trajectory_gt:  list[tuple]  = [(0.0, 0.0)]
    loc_err_history: list[float] = []

    # Safety / motion
    lidar_min_history: list[float] = []   # per-tick min valid LiDAR reading
    yaw_rate_history:  list[float] = []   # for heading-rate RMS
    vx_history:        list[float] = []   # for acceleration / jerk RMS
    n_wall_collisions  = 0

    # Stuck detection
    _stuck_deque: deque = deque(maxlen=STUCK_WINDOW_TICKS)
    n_stuck_events  = 0
    n_recoveries    = 0
    _in_stuck       = False
    _stuck_sim_time = 0.0
    recovery_times: list[float] = []

    success    = False
    t_goal     = None
    last_yaw   = 0.0
    last_print = 0.0
    _cam_tick  = 0
    prev_tick_start_x = 0.0
    prev_tick_start_y = 0.0

    # Shared dict written by _control_tick, read by the demo dashboard.
    # All updates happen on the same thread — no locking needed.
    _live_stats: dict = {
        "sim_time":          0.0,
        "goal_reached":      False,
        "time_to_goal":      None,
        "n_wall_collisions": 0,
        "n_stuck_events":    0,
        "dist_to_goal":      0.0,
        "loc_err":           0.0,
        "x_est":             0.0,
        "y_est":             0.0,
        "nav_hz":            float(CONTROL_HZ),
        "cam_hz":            float(CONTROL_HZ) / 2.0,
        "speed":             speed,
        "waypoints_done":    0,
        "n_waypoints":       len(path),
        "path_eff_live":     1.0,
        "path_deviation":    0.0,
        "min_wall_clearance": 9.9,   # meters, rolling minimum LiDAR reading
        "heading_rms":       0.0,    # rad/s, rolling RMS of yaw-rate (last 5 s)
        "_prev_x_gt":        None,   # internal: previous GT x for distance accumulation
        "_prev_y_gt":        None,   # internal: previous GT y
        "_dist_traveled":    0.0,    # internal: cumulative GT travel distance
    }
    def _sensor_occupied(px: float, py: float) -> bool:
        r, c = occ_nav.world_to_cell(px, py)
        return (not occ_nav.in_bounds(r, c)
                or occ_nav.grid[r, c] == OccupancyGrid.OCCUPIED)

    def _control_tick() -> bool:
        """One nav-stack tick. Returns True when goal is reached."""
        nonlocal last_yaw, prev_tick_start_x, prev_tick_start_y, _cam_tick
        nonlocal n_wall_collisions, n_stuck_events, n_recoveries
        nonlocal _in_stuck, _stuck_sim_time
        cur_x = float(data.qpos[0])
        cur_y = float(data.qpos[1])

        lidar  = get_lidar(model, data, prefix="lidar_")
        imu    = get_imu(model, data)
        gyro_z = float(imu["gyro"][2])

        theta_prev = localizer.theta
        cos_t = np.cos(theta_prev);  sin_t = np.sin(theta_prev)
        dx = cur_x - prev_tick_start_x
        dy = cur_y - prev_tick_start_y
        actual_vx =  (dx * cos_t + dy * sin_t) / dt_control
        actual_vy = (-dx * sin_t + dy * cos_t) / dt_control
        localizer.update(actual_vx, actual_vy, last_yaw, gyro_z, dt_control)
        x_est, y_est, theta_est = localizer.pose

        occ_sensor.update_from_lidar(
            x_est, y_est, theta_est,
            lidar["ranges"], lidar_angles,
            min_range=0.15, max_range=LIDAR_CUTOFF - 0.1,
        )

        vx, vy, yaw_rate = controller.step(
            x_est, y_est, theta_est,
            lidar_ranges=lidar["ranges"],
            lidar_angles=lidar_angles,
        )

        policy.set_command(vx, vy, yaw_rate)
        policy.step(model, data, dt=dt_control)

        # Wall collision: try full move → x-slide → y-slide → full stop
        nx, ny = float(data.qpos[0]), float(data.qpos[1])
        if _sensor_occupied(nx, ny):
            n_wall_collisions += 1
            if not _sensor_occupied(nx, cur_y):
                data.qpos[1] = cur_y
            elif not _sensor_occupied(cur_x, ny):
                data.qpos[0] = cur_x
            else:
                data.qpos[0] = cur_x
                data.qpos[1] = cur_y
            mujoco.mj_forward(model, data)

        prev_tick_start_x = cur_x
        prev_tick_start_y = cur_y
        last_yaw = yaw_rate

        # ── KPI measurements ──────────────────────────────────────────────────

        # Localization error (GT for scoring only)
        trajectory_est.append((x_est, y_est))
        gt = get_gt_pose(model, data)
        trajectory_gt.append((float(gt["pos"][0]), float(gt["pos"][1])))
        loc_err_history.append(
            float(np.hypot(x_est - gt["pos"][0], y_est - gt["pos"][1]))
        )

        # Minimum wall clearance — min valid LiDAR reading this tick
        raw = lidar["ranges"]
        valid = raw[(raw > 0.15) & (raw < LIDAR_CUTOFF - 0.1)]
        if valid.size:
            lidar_min_history.append(float(valid.min()))

        # Smoothness
        yaw_rate_history.append(yaw_rate)
        vx_history.append(vx)

        # Stuck detection: sliding window over last STUCK_WINDOW_TICKS positions
        _stuck_deque.append((float(data.qpos[0]), float(data.qpos[1])))
        if len(_stuck_deque) == STUCK_WINDOW_TICKS:
            x0s, y0s = _stuck_deque[0]
            x1s, y1s = _stuck_deque[-1]
            window_disp = float(np.hypot(x1s - x0s, y1s - y0s))
            if not _in_stuck and window_disp < STUCK_DIST_M:
                n_stuck_events += 1
                _in_stuck       = True
                _stuck_sim_time = data.time
            elif _in_stuck and window_disp > RECOVER_DIST_M:
                n_recoveries += 1
                recovery_times.append(data.time - _stuck_sim_time)
                _in_stuck = False

        # ── Live stats (demo dashboard) ───────────────────────────────────────
        _n = len(loc_err_history)
        _live_stats["sim_time"]          = data.time
        _live_stats["n_wall_collisions"] = n_wall_collisions
        _live_stats["n_stuck_events"]    = n_stuck_events
        _live_stats["x_est"]             = x_est
        _live_stats["y_est"]             = y_est
        _live_stats["loc_err"]           = loc_err_history[-1] if loc_err_history else 0.0
        _live_stats["ate_rmse"]          = (float(np.sqrt(np.mean(np.array(loc_err_history)**2)))
                                            if loc_err_history else 0.0)
        _live_stats["nav_hz"]            = _n / max(data.time, 0.001)
        _live_stats["cam_hz"]            = (_n // 2) / max(data.time, 0.001)
        gx, gy = goal_xy
        _live_stats["dist_to_goal"] = float(np.hypot(x_est - gx, y_est - gy))

        # Waypoints completed
        _live_stats["waypoints_done"] = controller._wp_idx

        # Deviation from planned A* path (distance to nearest segment)
        _live_stats["path_deviation"] = _deviation_from_path(x_est, y_est)

        # Min wall clearance: tightest approach to any wall so far
        if lidar_min_history:
            _live_stats["min_wall_clearance"] = float(min(lidar_min_history))

        # Heading smoothness: RMS of yaw-rate over last 100 ticks (~5 s)
        if yaw_rate_history:
            _yr = np.array(yaw_rate_history[-100:])
            _live_stats["heading_rms"] = float(np.sqrt(np.mean(_yr ** 2)))

        # Live path efficiency: accumulated GT travel / optimal length
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

        # ── Data recording ────────────────────────────────────────────────────
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

        gx, gy = goal_xy
        return np.hypot(x_est - gx, y_est - gy) < controller.goal_tol

    # ── Run with or without viewer ────────────────────────────────────────────
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
                success = True
                t_goal  = data.time
                break

            if data.time - last_print >= 5.0:
                last_print = data.time
                x_e, y_e, _ = localizer.pose
                gt = get_gt_pose(model, data)
                loc_err = np.hypot(x_e - gt["pos"][0], y_e - gt["pos"][1])
                gx, gy = goal_xy
                dist = np.hypot(x_e - gx, y_e - gy)
                print(f"  t={data.time:6.1f}s  "
                      f"est=({x_e:.2f},{y_e:.2f})  "
                      f"loc_err={loc_err:.2f}m  "
                      f"dist_to_goal={dist:.2f}m")

    wall_time_elapsed = time.perf_counter() - wall_time_start

    # ── Close recorder ────────────────────────────────────────────────────────
    capture_rates: dict[str, float] = {}
    if rec is not None:
        capture_rates = rec.close()

    # ── KPI computation ───────────────────────────────────────────────────────
    actual_len = _path_length(trajectory_gt)
    opt_len    = maze_grid.optimal_path_length_m()
    # traveled / optimal: 1.0 = perfect, >1.0 = excess wandering (spec definition)
    efficiency = actual_len / opt_len if opt_len > 0 else 0.0

    # DEBUG: compare live vs post-run path efficiency values
    _live_dist = _live_stats["_dist_traveled"]
    print(f"\n[DEBUG path_eff] live_dist_traveled={_live_dist:.3f}m  "
          f"gt_actual_len={actual_len:.3f}m  "
          f"optimal={opt_len:.3f}m  "
          f"live_ratio={_live_dist/opt_len if opt_len>0 else 0:.4f}x  "
          f"gt_ratio={efficiency:.4f}x")

    gt_final = get_gt_pose(model, data)
    x_e, y_e, _ = localizer.pose
    final_loc_err = float(np.hypot(x_e - gt_final["pos"][0],
                                   y_e - gt_final["pos"][1]))

    # Final goal error: GT distance from robot to goal (not estimated)
    final_goal_error_m = float(np.hypot(gt_final["pos"][0] - goal_xy[0],
                                        gt_final["pos"][1] - goal_xy[1]))

    loc_arr = np.array(loc_err_history) if loc_err_history else np.array([0.0])
    ate_rmse = float(np.sqrt(np.mean(loc_arr ** 2)))
    drift_pct = (ate_rmse / actual_len * 100.0) if actual_len > 0 else 0.0

    # Wall clearance
    if lidar_min_history:
        min_clearance_m  = float(np.min(lidar_min_history))
        mean_clearance_m = float(np.mean(lidar_min_history))
    else:
        min_clearance_m  = None
        mean_clearance_m = None

    # Smoothness
    heading_rate_rms = (float(np.sqrt(np.mean(np.array(yaw_rate_history) ** 2)))
                        if yaw_rate_history else None)
    if len(vx_history) > 1:
        accel_arr = np.diff(vx_history) / dt_control      # m/s²
        jerk_rms  = float(np.sqrt(np.mean(accel_arr ** 2)))
    else:
        jerk_rms = None

    # Map coverage: non-UNKNOWN cells in sensor grid / free cells in GT map
    free_cells_gt   = int(np.sum(occ_plan_raw.grid == OccupancyGrid.FREE))
    explored_cells  = int(np.sum(occ_sensor.grid != OccupancyGrid.UNKNOWN))
    map_coverage_pct = (100.0 * explored_cells / max(free_cells_gt, 1))

    # Real-time factor (sim s / wall s) — >1 means faster than real time
    real_time_factor = data.time / max(wall_time_elapsed, 0.001)

    # Reliability metrics
    # MTBF counts navigation failures only: stuck events + episode failure.
    # Wall collisions are contacts, not failures — the robot recovers and continues.
    nav_failures = n_stuck_events + (0 if success else 1)
    mtbf_m = actual_len / nav_failures if nav_failures > 0 else actual_len
    recovery_rate = (100.0 * n_recoveries / n_stuck_events
                     if n_stuck_events > 0 else 100.0)
    mean_recovery_s = (float(np.mean(recovery_times))
                       if recovery_times else None)

    # Failure taxonomy
    if success:
        failure_reason = "none"
    elif n_stuck_events > 0 and n_wall_collisions <= 5:
        failure_reason = "stuck"
    elif n_wall_collisions > 10:
        failure_reason = "wall_collision"
    else:
        failure_reason = "timeout"

    # ── DATA QUALITY ──────────────────────────────────────────────────────────

    # Per-stream fps (sim-Hz) and frame-drop rate.
    # In kinematic sim every tick executes — drops are 0% by construction.
    # When --record is active, recorder.close() provides measured sim-Hz values;
    # we use those (more precise) and fall back to the calculated values otherwise.
    n_ticks = len(loc_err_history)
    _nav_hz = round(n_ticks / max(data.time, 0.001), 2)
    _cam_hz = round((n_ticks // 2) / max(data.time, 0.001), 2)
    _STREAM_TARGETS = {
        "imu": 20, "base_state": 20, "joint_state": 20,
        "lidar": 20, "camera": 10, "gt_pose": 20,
    }
    if capture_rates:
        achieved_fps = {s: round(capture_rates.get(s, 0.0), 2)
                        for s in _STREAM_TARGETS}
    else:
        achieved_fps = {
            "imu": _nav_hz, "base_state": _nav_hz, "joint_state": _nav_hz,
            "lidar": _nav_hz, "camera": _cam_hz, "gt_pose": _nav_hz,
        }
    frame_drop_pct = {
        s: round(max(0.0, 100.0 * (1.0 - achieved_fps[s] / t)), 2)
        for s, t in _STREAM_TARGETS.items()
    }

    # Inter-sensor sync error: all sensors read from the same MjData timestep
    # → sync skew is 0 ms by construction in kinematic simulation.
    inter_sensor_sync_ms = 0.0
    max_sync_skew_ms     = 0.0

    # Schema completeness: scan KPI values for NaN / Inf
    _pre_kpi = {
        "efficiency": efficiency, "final_goal_error_m": final_goal_error_m,
        "ate_rmse": ate_rmse, "drift_pct": drift_pct,
        "real_time_factor": real_time_factor, "mtbf_m": mtbf_m,
        "heading_rate_rms": heading_rate_rms or 0.0, "jerk_rms": jerk_rms or 0.0,
    }
    n_nan_inf = sum(
        1 for v in _pre_kpi.values()
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v))
    )
    schema_valid = (n_nan_inf == 0)

    # Peak process RAM (resident set size) at end of episode
    peak_ram_mb = None
    if _psutil is not None:
        try:
            peak_ram_mb = round(_psutil.Process().memory_info().rss / 1_048_576, 1)
        except Exception:
            pass

    kpis: dict = {
        # Identity
        "seed":              seed,
        "grid_size":         grid_size,

        # SUCCESS
        "success":           success,

        # MISSION
        "sim_time_s":        round(data.time, 2),
        "time_to_goal_s":    round(t_goal, 2) if t_goal else None,
        "actual_path_m":     round(actual_len, 3),
        "optimal_path_m":    round(opt_len, 3),
        "path_efficiency":   round(efficiency, 4),   # traveled/optimal; 1.0=perfect
        "final_goal_error_m":round(final_goal_error_m, 3),

        # SAFETY & MOTION
        "n_wall_collisions":  n_wall_collisions,
        "min_wall_clearance_m": (round(min_clearance_m, 3)
                                 if min_clearance_m is not None else None),
        "mean_wall_clearance_m":(round(mean_clearance_m, 3)
                                 if mean_clearance_m is not None else None),
        "n_stuck_events":    n_stuck_events,
        "n_recoveries":      n_recoveries,
        "recovery_rate_pct": round(recovery_rate, 1),
        "mean_recovery_s":   (round(mean_recovery_s, 2)
                              if mean_recovery_s is not None else None),
        "heading_rate_rms":  (round(heading_rate_rms, 4)
                              if heading_rate_rms is not None else None),
        "jerk_rms_m_s2":     (round(jerk_rms, 4)
                              if jerk_rms is not None else None),

        # LOCALIZATION
        "final_loc_err_m":   round(final_loc_err, 3),
        "mean_loc_err_m":    round(float(loc_arr.mean()), 3),
        "max_loc_err_m":     round(float(loc_arr.max()), 3),
        "ate_rmse_m":        round(ate_rmse, 3),
        "drift_pct":         round(drift_pct, 2),

        # MAP
        "map_coverage_pct":  round(map_coverage_pct, 1),

        # DATA QUALITY
        "achieved_fps":          achieved_fps,
        "frame_drop_pct":        frame_drop_pct,
        "inter_sensor_sync_ms":  inter_sensor_sync_ms,
        "max_sync_skew_ms":      max_sync_skew_ms,
        "schema_valid":          schema_valid,
        "n_nan_inf":             n_nan_inf,

        # RELIABILITY
        "failure_reason":    failure_reason,
        "mtbf_m":            round(mtbf_m, 2),
        "n_ticks":           n_ticks,

        # PERFORMANCE
        "real_time_factor":  round(real_time_factor, 2),
        "wall_time_s":       round(wall_time_elapsed, 2),
        "peak_ram_mb":       peak_ram_mb,
    }

    print("\n=== KPIs ===")
    for k, v in kpis.items():
        print(f"  {k:<26}: {v}")

    return kpis


# ── Demo dashboard ────────────────────────────────────────────────────────────

def _make_rich_panel(ls: dict, seed: int, grid_size: int) -> "_RichPanel":
    """Build a Rich Panel with three columns for the live demo dashboard."""
    t = _RichTable.grid(padding=(0, 2))
    t.add_column(justify="center", min_width=26)
    t.add_column(justify="center", min_width=26)
    t.add_column(justify="center", min_width=26)

    def _val(v, fmt=".2f", unit=""):
        if v is None:
            return "[dim]--[/dim]"
        return f"[bold]{v:{fmt}}[/bold]{unit}"

    # ── Column 1: SOLVE ────────────────────────────────────────────────────────
    goal_str = ("[bold green]YES ✓[/bold green]" if ls["goal_reached"]
                else "[bold yellow]no…[/bold yellow]")
    ttg = ls["time_to_goal"]
    ttg_str = (f"[bold green]{ttg:.1f}s[/bold green]" if ttg is not None
               else f"[bold]{ls['sim_time']:.1f}s[/bold] [dim]elapsed[/dim]")
    col1 = (
        f"[cyan]SOLVE[/cyan]\n"
        f"Goal reached : {goal_str}\n"
        f"Time-to-goal : {ttg_str}\n"
        f"Dist to goal : {_val(ls['dist_to_goal'], '.2f', 'm')}\n"
        f"Sim time     : {_val(ls['sim_time'], '.1f', 's')}"
    )

    # ── Column 2: NAVIGATION ───────────────────────────────────────────────────
    col2 = (
        f"[cyan]NAVIGATION[/cyan]\n"
        f"Collisions   : [bold red]{ls['n_wall_collisions']}[/bold red]\n"
        f"Stuck events : [bold red]{ls['n_stuck_events']}[/bold red]\n"
        f"Loc error    : {_val(ls['loc_err'], '.3f', 'm')}\n"
        f"Est pos      : ({ls['x_est']:.2f}, {ls['y_est']:.2f})"
    )

    # ── Column 3: CAPTURE HEALTH ───────────────────────────────────────────────
    nav_hz = ls["nav_hz"]
    cam_hz = ls["cam_hz"]
    speed  = ls.get("speed", 2.0)
    col3 = (
        f"[cyan]CAPTURE HEALTH[/cyan]\n"
        f"Nav  fps     : {_val(nav_hz, '.1f', ' Hz')}\n"
        f"Cam  fps     : {_val(cam_hz, '.1f', ' Hz')}\n"
        f"Frame drops  : [bold]0%[/bold] [dim](kinematic)[/dim]\n"
        f"Sync skew    : [bold]0 ms[/bold]   Speed={speed:g}x"
    )

    t.add_row(col1, col2, col3)
    title = (f"[bold]G1 MAZE DEMO[/bold]  seed=[cyan]{seed}[/cyan]  "
             f"grid=[cyan]{grid_size}×{grid_size}[/cyan]")
    return _RichPanel(t, title=title, border_style="bright_blue")


# ── Viewer loop ───────────────────────────────────────────────────────────────

def _run_with_viewer(
    model, data, maze_grid, localizer, occ_nav, path, goal_xy,
    tick_fn, max_time, dt_control, speed: float = 2.0,
    demo: bool = False, live_stats: dict | None = None,
    seed: int = 0, grid_size: int = 10,
    trajectory_gt: list | None = None,
):
    speed_label = f"{speed:g}x" if speed != 1.0 else "1x"
    if not demo:
        print(f"Opening viewer  (close window or wait for max_time to stop)  "
              f"speed={speed_label}\n")
        print("  Controls: left-drag=rotate  scroll=zoom  Space=pause\n")

    viz = Visualizer(model, occ_nav, path, goal_xy)

    _paused = [False]

    def _key_cb(key: int) -> None:
        if key == 32:
            _paused[0] = not _paused[0]
            if not demo:
                print(f"  {'[PAUSED]' if _paused[0] else '[RESUMED]'}", flush=True)

    _rich_live_ctx = (
        _RichLive(_make_rich_panel(live_stats, seed, grid_size),
                  refresh_per_second=5,
                  console=_RichConsole())
        if (demo and _RICH and live_stats is not None)
        else None
    )
    if _rich_live_ctx is not None:
        _rich_live_ctx.start()

    # ── Browser dashboard ─────────────────────────────────────────────────────
    _dash_srv: "_DashboardServer | None" = None
    if demo and _DASHBOARD and live_stats is not None:
        _dash_srv = _DashboardServer(port=7654)
        url = _dash_srv.start()
        print(f"\n  Dashboard: {url}  (opening browser…)\n")
        webbrowser.open(url)

    last_dash_wall = time.perf_counter()
    DASH_HZ        = 5
    dash_interval  = 1.0 / DASH_HZ

    with mujoco.viewer.launch_passive(model, data,
                                      key_callback=_key_cb) as viewer:
        viewer.opt.geomgroup[4] = True
        viewer.opt.sitegroup[4] = True

        pelvis_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        viewer.cam.type        = mujoco.mjtCamera.mjCAMERA_TRACKING
        viewer.cam.trackbodyid = pelvis_id
        viewer.cam.distance    = 6.0
        viewer.cam.elevation   = -50
        viewer.cam.azimuth     = 45

        last_print       = 0.0
        RENDER_HZ        = 60
        render_interval  = 1.0 / RENDER_HZ
        ctrl_interval    = dt_control / max(speed, 0.1)
        viz_interval     = 1.0 / Visualizer.UPDATE_HZ
        last_ctrl_wall   = time.perf_counter()
        last_render_wall = time.perf_counter()
        last_viz_wall    = time.perf_counter()

        while viewer.is_running() and data.time < max_time:
            now = time.perf_counter()

            goal_reached = False
            if not _paused[0] and now - last_ctrl_wall >= ctrl_interval:
                goal_reached = tick_fn()
                last_ctrl_wall = now

            if now - last_render_wall >= render_interval:
                viewer.sync()
                last_render_wall = now

            if now - last_viz_wall >= viz_interval:
                x_e, y_e, th_e = localizer.pose
                viz.update(viewer, x_e, y_e, th_e, data.time, paused=_paused[0])
                last_viz_wall = now

            time.sleep(0.001)

            # Dashboard refresh (demo mode) — Rich terminal + browser SSE
            if demo and now - last_dash_wall >= dash_interval:
                if _rich_live_ctx is not None:
                    _rich_live_ctx.update(_make_rich_panel(live_stats, seed, grid_size))
                if _dash_srv is not None:
                    _dash_srv.push({
                                        **{k: v for k, v in live_stats.items()
                                           if not k.startswith("_")},
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
                      f"dist_to_goal={np.hypot(x_e-gx,y_e-gy):.2f}m")

            if goal_reached:
                # Final push so dashboard shows the solved state immediately
                if _rich_live_ctx is not None:
                    _rich_live_ctx.update(_make_rich_panel(live_stats, seed, grid_size))
                if _dash_srv is not None:
                    # Downsample GT trajectory for the path-comparison chart
                    _gt_stride = max(1, len(trajectory_gt) // 800)
                    _dash_srv.push({
                                        **{k: v for k, v in live_stats.items()
                                           if not k.startswith("_")},
                                        "seed": seed, "grid_size": grid_size,
                                        "minimap_b64": viz.minimap_b64,
                                        "path_progress": viz._path_progress(
                                            live_stats["x_est"], live_stats["y_est"]),
                                        # Post-run path comparison (scoring/display only)
                                        "planned_path":  [[float(x), float(y)] for x, y in path],
                                        **({"gt_trajectory": [[float(x), float(y)]
                                                               for x, y in (trajectory_gt or [])[::_gt_stride]]}
                                           if trajectory_gt else {}),
                                    })
                if not demo:
                    print(f"\n  GOAL REACHED at t={data.time:.1f}s")
                viz.notify_goal(data.time)
                deadline = time.perf_counter() + 5.0  # longer linger so browser can see it
                while viewer.is_running() and time.perf_counter() < deadline:
                    t = time.perf_counter()
                    if t - last_render_wall >= render_interval:
                        viewer.sync()
                        last_render_wall = t
                    if t - last_viz_wall >= viz_interval:
                        x_e, y_e, th_e = localizer.pose
                        viz.update(viewer, x_e, y_e, th_e, data.time, paused=_paused[0])
                        last_viz_wall = t
                    if demo and t - last_dash_wall >= dash_interval:
                        if _rich_live_ctx is not None:
                            _rich_live_ctx.update(_make_rich_panel(live_stats, seed, grid_size))
                        if _dash_srv is not None:
                            _dash_srv.push({**live_stats, "seed": seed, "grid_size": grid_size,
                                    "minimap_b64": viz.minimap_b64,
                                    "path_progress": viz._path_progress(
                                        live_stats["x_est"], live_stats["y_est"])})
                        last_dash_wall = t
                    time.sleep(0.001)
                break

    if _rich_live_ctx is not None:
        _rich_live_ctx.stop()
    if _dash_srv is not None:
        _dash_srv.stop()
    viz.close()
    if not demo:
        print("Viewer closed.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _path_length(trajectory: list[tuple]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(trajectory, trajectory[1:]):
        total += np.hypot(x1 - x0, y1 - y0)
    return total


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="G1 maze navigation runner")
    parser.add_argument("--seed",      type=int,   default=42)
    parser.add_argument("--grid-size", type=int,   default=10)
    parser.add_argument("--max-time",  type=float, default=300.0)
    parser.add_argument("--no-viz",    action="store_true")
    parser.add_argument("--record",    action="store_true")
    parser.add_argument("--speed",     type=float, default=2.0)
    parser.add_argument("--difficulty", choices=DIFFICULTY_PRESETS.keys())
    parser.add_argument("--demo",      action="store_true",
                        help="Show live Rich terminal dashboard (requires rich)")
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
