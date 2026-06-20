"""
make_grid_compare.py
Side-by-side minimap video: normal robot (left) vs dynamic obstacle (right).
Seed 42, 2x1 grid, rendered at ~10x sim speed.

Usage:
    conda run -n robotics-assignment python make_grid_compare.py
Output: report/grid_compare.mp4
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from math import cos, sin
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.colors import LinearSegmentedColormap
import imageio_ffmpeg
import mujoco

ROOT = Path(__file__).parent
matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
sys.path.insert(0, str(ROOT))

from maze.generator    import MazeGrid, MazeScene
from robot.sensors     import get_lidar, get_imu
from robot.walking_policy.interface import WalkingPolicyInterface
from navigation.occupancy_grid import OccupancyGrid
from navigation.localization   import Localizer
from navigation.controller     import PurePursuitController

# ── Config ────────────────────────────────────────────────────────────────────
SEED            = 42
GRID_SIZE       = 10
CELL_PX         = 520          # pixel width of each cell
VIDEO_FPS       = 15
TICKS_PER_FRAME = 6            # 6 × (1/20 Hz) = 0.3 s/frame ≈ 4.5x sim speed
MAX_SIM_TIME    = 300.0
CONTROL_HZ      = 20
INFLATE_R       = 3
N_LIDAR         = 16
LIDAR_FOV       = np.deg2rad(270)
LIDAR_CUTOFF    = 10.0
DT              = 1.0 / CONTROL_HZ

# Moving-wall parameters (mirror runner_dynamic.py)
_WALL_SPEED   = 0.18
_INTRO_DELAY  = 10.0
_BLOCK_DWELL  = 8.0
_CLEAR_DWELL  = 10.0
_STOP_DIST    = 0.35
_GO_DIST      = 0.55
_SAFE_STOP_DIST = 1.0
_ENGAGE_DIST  = 4.0

G1_SCENE = ROOT / "robot" / "model" / "g1" / "scene.xml"
OUT_PATH  = ROOT / "report" / "grid_compare.mp4"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _find_body(body, name):
    if body.name == name:
        return body
    for child in body.bodies:
        r = _find_body(child, name)
        if r:
            return r
    return None

def _pointing_quat(theta):
    s = np.sin(np.pi / 4)
    return [s, -s * np.sin(theta), s * np.cos(theta), 0.0]

def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)

def _wall_to_path_dist(wx, wy, path):
    min_d = float("inf")
    for i in range(len(path) - 1):
        ax, ay = path[i]; bx, by = path[i + 1]
        dx, dy = bx - ax, by - ay
        sq = dx*dx + dy*dy
        if sq < 1e-10:
            d = float(np.hypot(wx - ax, wy - ay))
        else:
            t = max(0.0, min(1.0, ((wx-ax)*dx + (wy-ay)*dy) / sq))
            d = float(np.hypot(wx-(ax+t*dx), wy-(ay+t*dy)))
        if d < min_d:
            min_d = d
    return min_d


# ── Scene builders ────────────────────────────────────────────────────────────
def _add_lidar(spec, torso):
    angles = np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR)
    hl = 0.12
    for i, theta in enumerate(angles):
        site = torso.add_site()
        site.name  = f"lidar_site_{i:02d}"
        site.type  = mujoco.mjtGeom.mjGEOM_SPHERE
        site.size  = [0.001, 0.001, 0.001]
        site.pos   = [hl * np.cos(theta), hl * np.sin(theta), 0.0]
        site.quat  = _pointing_quat(theta)
        site.rgba  = [0.0, 0.0, 0.0, 0.0]
        site.group = 5
    for i in range(N_LIDAR):
        s = spec.add_sensor()
        s.name    = f"lidar_{i:02d}"
        s.type    = mujoco.mjtSensor.mjSENS_RANGEFINDER
        s.objtype = mujoco.mjtObj.mjOBJ_SITE
        s.objname = f"lidar_site_{i:02d}"
        s.cutoff  = LIDAR_CUTOFF


def build_normal_scene(seed):
    grid  = MazeGrid(seed=seed, grid_size=GRID_SIZE)
    scene = MazeScene(grid, G1_SCENE)
    _, spec = scene.build()
    torso = _find_body(spec.worldbody, "torso_link")
    _add_lidar(spec, torso)
    model = spec.compile()
    data  = mujoco.MjData(model)
    return model, data, grid


def build_dynamic_scene(seed):
    grid  = MazeGrid(seed=seed, grid_size=GRID_SIZE)
    scene = MazeScene(grid, G1_SCENE)
    _, spec = scene.build()
    torso = _find_body(spec.worldbody, "torso_link")
    _add_lidar(spec, torso)

    wall           = spec.worldbody.add_body()
    wall.name      = "moving_wall"
    wall.mocap     = True
    wall.pos       = [0.0, 0.0, -10.0]
    panel          = wall.add_geom()
    panel.type     = mujoco.mjtGeom.mjGEOM_BOX
    panel.size     = [0.06, 0.75, 1.0]
    panel.pos      = [0.0, 0.0, 1.0]
    panel.rgba     = [0.2, 0.5, 0.9, 0.85]
    panel.contype  = 0
    panel.conaffinity = 0

    model = spec.compile()
    data  = mujoco.MjData(model)
    return model, data, grid


# ── Simulation state ──────────────────────────────────────────────────────────
@dataclass
class Sim:
    label:        str
    model:        object
    data:         object
    policy:       object
    localizer:    object
    controller:   object
    occ_nav:      object
    occ_raw:      object
    lidar_angles: np.ndarray
    goal_xy:      tuple
    path:         list
    # dynamic-only fields
    wall_mocap_id: int | None = None
    wall_pos:     np.ndarray  = field(default_factory=lambda: np.zeros(3))
    wall_axis:    int         = 1
    wall_block_v: float       = 0.0
    wall_clear_v: float       = 0.0
    wall_phase:   str         = "intro"
    wall_phase_end: float     = 0.0
    wall_slide_from: float    = 0.0
    wall_slide_to:   float    = 0.0
    wall_slide_dur:  float    = 0.0
    ob_state:     str         = "CLEAR"
    ob_waits:     int         = 0
    ob_cooldown_end: float    = 0.0
    # tracking
    traj_x: list = field(default_factory=list)
    traj_y: list = field(default_factory=list)
    last_yaw: float = 0.0
    prev_x:   float = 0.0
    prev_y:   float = 0.0
    done:     bool  = False
    success:  bool  = False
    wall_xy:  tuple = (None, None)   # for drawing wall dot


def _occupied(occ_nav, px, py):
    r, c = occ_nav.world_to_cell(px, py)
    return not occ_nav.in_bounds(r, c) or occ_nav.grid[r, c] == OccupancyGrid.OCCUPIED


def step(s: Sim):
    if s.done:
        return

    cur_x = float(s.data.qpos[0])
    cur_y = float(s.data.qpos[1])

    # ── Moving wall (dynamic sim only) ────────────────────────────────────────
    if s.wall_mocap_id is not None:
        t = s.data.time
        slide_dist = abs(s.wall_clear_v - s.wall_block_v)
        slide_dur  = slide_dist / _WALL_SPEED

        if s.wall_phase == "intro" and t >= s.wall_phase_end:
            s.wall_phase      = "slide_to_block"
            s.wall_slide_from = s.wall_clear_v
            s.wall_slide_to   = s.wall_block_v
            s.wall_slide_dur  = slide_dur
            s.wall_phase_end  = t + slide_dur

        elif s.wall_phase == "slide_to_block":
            elapsed = t - (s.wall_phase_end - s.wall_slide_dur)
            alpha   = _smoothstep(elapsed / max(s.wall_slide_dur, 1e-6))
            s.wall_pos[s.wall_axis] = s.wall_slide_from + (s.wall_slide_to - s.wall_slide_from) * alpha
            if t >= s.wall_phase_end:
                s.wall_pos[s.wall_axis] = s.wall_block_v
                s.wall_phase     = "dwell_block"
                s.wall_phase_end = t + _BLOCK_DWELL

        elif s.wall_phase == "dwell_block" and t >= s.wall_phase_end:
            s.wall_phase      = "slide_to_clear"
            s.wall_slide_from = s.wall_block_v
            s.wall_slide_to   = s.wall_clear_v
            s.wall_slide_dur  = slide_dur
            s.wall_phase_end  = t + slide_dur

        elif s.wall_phase == "slide_to_clear":
            elapsed = t - (s.wall_phase_end - s.wall_slide_dur)
            alpha   = _smoothstep(elapsed / max(s.wall_slide_dur, 1e-6))
            s.wall_pos[s.wall_axis] = s.wall_slide_from + (s.wall_slide_to - s.wall_slide_from) * alpha
            if t >= s.wall_phase_end:
                s.wall_pos[s.wall_axis] = s.wall_clear_v
                s.wall_phase     = "dwell_clear"
                s.wall_phase_end = t + _CLEAR_DWELL

        elif s.wall_phase == "dwell_clear" and t >= s.wall_phase_end:
            s.wall_phase      = "slide_to_block"
            s.wall_slide_from = s.wall_clear_v
            s.wall_slide_to   = s.wall_block_v
            s.wall_slide_dur  = slide_dur
            s.wall_phase_end  = t + slide_dur

        s.data.mocap_pos[s.wall_mocap_id] = s.wall_pos
        s.wall_xy = (float(s.wall_pos[0]), float(s.wall_pos[1]))

    # ── Sensors + localisation ────────────────────────────────────────────────
    lidar  = get_lidar(s.model, s.data, prefix="lidar_")
    imu    = get_imu(s.model, s.data)
    gyro_z = float(imu["gyro"][2])

    cos_t = np.cos(s.localizer.theta)
    sin_t = np.sin(s.localizer.theta)
    dx = cur_x - s.prev_x
    dy = cur_y - s.prev_y
    s.localizer.update(
        (dx * cos_t + dy * sin_t) / DT,
        (-dx * sin_t + dy * cos_t) / DT,
        s.last_yaw, gyro_z, DT,
    )
    x_est, y_est, theta_est = s.localizer.pose

    # ── Controller ────────────────────────────────────────────────────────────
    vx, vy, yaw_rate = s.controller.step(
        x_est, y_est, theta_est,
        lidar_ranges=lidar["ranges"],
        lidar_angles=s.lidar_angles,
    )

    # ── Moving-wall stop/go (dynamic only) ───────────────────────────────────
    if s.wall_mocap_id is not None:
        robot_to_wall = float(np.hypot(x_est - s.wall_pos[0], y_est - s.wall_pos[1]))
        if robot_to_wall < _ENGAGE_DIST:
            wall_d = _wall_to_path_dist(float(s.wall_pos[0]), float(s.wall_pos[1]), s.path)
            if (s.ob_state == "CLEAR"
                    and wall_d < _STOP_DIST
                    and robot_to_wall < _SAFE_STOP_DIST
                    and s.data.time >= s.ob_cooldown_end):
                s.ob_state  = "WAITING"
                s.ob_waits += 1
            elif s.ob_state == "WAITING" and wall_d >= _GO_DIST:
                s.ob_state        = "CLEAR"
                s.ob_cooldown_end = s.data.time + _BLOCK_DWELL + _CLEAR_DWELL
        elif s.ob_state == "WAITING":
            s.ob_state = "CLEAR"

        if s.ob_state == "WAITING":
            vx = 0.0; vy = 0.0; yaw_rate = 0.0

    # ── Physics step ─────────────────────────────────────────────────────────
    s.policy.set_command(vx, vy, yaw_rate)
    s.policy.step(s.model, s.data, dt=DT)

    nx, ny = float(s.data.qpos[0]), float(s.data.qpos[1])
    if _occupied(s.occ_nav, nx, ny):
        if not _occupied(s.occ_nav, nx, cur_y):
            s.data.qpos[1] = cur_y
        elif not _occupied(s.occ_nav, cur_x, ny):
            s.data.qpos[0] = cur_x
        else:
            s.data.qpos[0] = cur_x
            s.data.qpos[1] = cur_y
        mujoco.mj_forward(s.model, s.data)

    s.prev_x   = cur_x
    s.prev_y   = cur_y
    s.last_yaw = yaw_rate
    s.traj_x.append(x_est)
    s.traj_y.append(y_est)

    gx, gy = s.goal_xy
    if np.hypot(x_est - gx, y_est - gy) < 0.35:
        s.done = True; s.success = True
    elif s.data.time >= MAX_SIM_TIME:
        s.done = True


# ── Build both simulations ────────────────────────────────────────────────────
def _init_sim(model, data, grid, label, wall_mocap_id=None,
              wall_pos=None, wall_axis=1, wall_block_v=0.0, wall_clear_v=0.0):
    occ_raw = OccupancyGrid(resolution=0.1, x_min=-1, x_max=16, y_min=-1, y_max=16)
    occ_raw.load_from_maze(grid)
    occ_nav = occ_raw.inflated(INFLATE_R)

    path    = [(float(x), float(y)) for x, y in grid.solution_world_xy()]
    goal_xy = grid.cell_centre_world(*grid.goal_cell)

    theta0 = 0.0
    if len(path) >= 2:
        dx = path[1][0] - path[0][0]; dy = path[1][1] - path[0][1]
        theta0 = float(np.arctan2(dy, dx))

    mujoco.mj_resetDataKeyframe(model, data, 0)
    data.qpos[0], data.qpos[1] = 0.0, 0.0
    data.qpos[3] = np.cos(theta0 / 2)
    data.qpos[4] = 0.0
    data.qpos[5] = 0.0
    data.qpos[6] = np.sin(theta0 / 2)
    mujoco.mj_forward(model, data)

    policy     = WalkingPolicyInterface(model, backend="kinematic")
    localizer  = Localizer(x0=0.0, y0=0.0, theta0=theta0, rng_seed=SEED)
    controller = PurePursuitController(lookahead=0.6, max_vx=0.35,
                                       max_yaw=1.5, goal_tol=0.35)
    controller.set_path(path)

    s = Sim(
        label=label, model=model, data=data,
        policy=policy, localizer=localizer, controller=controller,
        occ_nav=occ_nav, occ_raw=occ_raw,
        lidar_angles=np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR),
        goal_xy=goal_xy, path=path,
        wall_mocap_id=wall_mocap_id,
        wall_pos=wall_pos if wall_pos is not None else np.zeros(3),
        wall_axis=wall_axis, wall_block_v=wall_block_v, wall_clear_v=wall_clear_v,
        wall_phase="intro", wall_phase_end=_INTRO_DELAY,
    )
    return s


print("Building normal simulation ...")
m_n, d_n, g_n = build_normal_scene(SEED)
sim_normal = _init_sim(m_n, d_n, g_n, label="Without Obstacle")

print("Building dynamic simulation ...")
m_d, d_d, g_d = build_dynamic_scene(SEED)

# Place moving wall (same logic as runner_dynamic.py)
wall_body_id  = mujoco.mj_name2id(m_d, mujoco.mjtObj.mjOBJ_BODY, "moving_wall")
wall_mocap_id = int(m_d.body_mocapid[wall_body_id])
path_d        = [(float(x), float(y)) for x, y in g_d.solution_world_xy()]
occ_raw_d     = OccupancyGrid(resolution=0.1, x_min=-1, x_max=16, y_min=-1, y_max=16)
occ_raw_d.load_from_maze(g_d)

wall_pos    = np.zeros(3)
wall_axis   = 1
wall_block_v = 0.0
wall_clear_v = 0.0
half_corr   = g_d.corridor_width / 2.0

for _i in range(6, len(path_d)):
    ax, ay = path_d[_i - 1]; bx, by = path_d[_i]
    if float(np.hypot(bx - ax, by - ay)) < 0.8:
        continue
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    in_x   = abs(bx - ax) >= abs(by - ay)
    if in_x:
        wall_axis    = 1
        wall_block_v = my
        cy_plus = occ_raw_d.world_to_cell(mx, my + half_corr + 0.6)
        if occ_raw_d.in_bounds(*cy_plus) and occ_raw_d.grid[cy_plus] != OccupancyGrid.OCCUPIED:
            wall_clear_v = my + half_corr + 0.6
        else:
            wall_clear_v = my - half_corr - 0.6
        wall_pos[:] = [mx, wall_clear_v, 0.0]
    else:
        wall_axis    = 0
        wall_block_v = mx
        cx_plus = occ_raw_d.world_to_cell(mx + half_corr + 0.6, my)
        if occ_raw_d.in_bounds(*cx_plus) and occ_raw_d.grid[cx_plus] != OccupancyGrid.OCCUPIED:
            wall_clear_v = mx + half_corr + 0.6
        else:
            wall_clear_v = mx - half_corr - 0.6
        wall_pos[:] = [wall_clear_v, my, 0.0]
    d_d.mocap_pos[wall_mocap_id] = wall_pos
    mujoco.mj_forward(m_d, d_d)
    print(f"  Wall placed at segment [{_i-1}->{_i}]  axis={'Y' if in_x else 'X'}  "
          f"block={wall_block_v:.2f}  clear={wall_clear_v:.2f}")
    break

sim_dynamic = _init_sim(m_d, d_d, g_d, label="With Dynamic Obstacle",
                        wall_mocap_id=wall_mocap_id,
                        wall_pos=wall_pos, wall_axis=wall_axis,
                        wall_block_v=wall_block_v, wall_clear_v=wall_clear_v)

sims = [sim_normal, sim_dynamic]

# ── Figure: 1 row × 2 columns ────────────────────────────────────────────────
print("Building figure ...")

MAZE_CMAP = LinearSegmentedColormap.from_list("maze", ["#ffffff", "#111111"], N=256)

fig_w = CELL_PX * 2 / 100
fig_h = CELL_PX / 100
fig, axes = plt.subplots(1, 2, figsize=(fig_w, fig_h), dpi=100)
fig.patch.set_facecolor("#000000")
plt.subplots_adjust(left=0.002, right=0.998, top=0.92, bottom=0.002,
                    wspace=0.02, hspace=0.0)

traj_lines   = []
robot_dots   = []
robot_dirs   = []
status_texts = []
wall_dots    = []

for s, ax in zip(sims, axes):
    ax.set_facecolor("#000000")
    occ = s.occ_nav
    extent = [occ.x_min, occ.x_min + occ.W * occ.res,
              occ.y_min, occ.y_min + occ.H * occ.res]
    ax.imshow(occ.grid, origin="lower", extent=extent,
              cmap=MAZE_CMAP, vmin=0, vmax=100, aspect="equal")

    if len(s.path) >= 2:
        px, py = zip(*s.path)
        ax.plot(px, py, color="#4fc3f7", lw=2.0, alpha=0.9, zorder=2)

    gx, gy = s.goal_xy
    ax.scatter([gx], [gy], c="#ffd54f", s=80, marker="*", zorder=4)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.axis("off")

    # Column title
    col_color = "#4fc3f7" if s.label == "Normal Robot" else "#ff7043"
    ax.set_title(s.label, color=col_color, fontsize=13, fontweight="bold", pad=6)

    tl, = ax.plot([], [], ".", color="#66bb6a", markersize=1.5, alpha=0.45, zorder=3)
    rd, = ax.plot([], [], "o", color="#ef5350", markersize=6, zorder=5)
    rdir, = ax.plot([], [], "-", color="#ef5350", lw=2.0, zorder=5)

    # Wall dot (only visible for dynamic sim)
    wd, = ax.plot([], [], "s", color="#ff7043", markersize=9,
                  markeredgecolor="#ffffff", markeredgewidth=0.8,
                  alpha=0.0, zorder=6)

    st = ax.text(0.03, 0.04, "", transform=ax.transAxes, fontsize=7.5,
                 va="bottom", color="#ffffff",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#000000", alpha=0.80),
                 zorder=7)

    ax.text(0.03, 0.97, f"seed {SEED}", transform=ax.transAxes, fontsize=7,
            va="top", color="#cccccc", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#000000", alpha=0.75),
            zorder=7)

    traj_lines.append(tl)
    robot_dots.append(rd)
    robot_dirs.append(rdir)
    wall_dots.append(wd)
    status_texts.append(st)


# ── Animation ─────────────────────────────────────────────────────────────────
def animate(frame):
    for i, s in enumerate(sims):
        if not s.done:
            for _ in range(TICKS_PER_FRAME):
                step(s)
                if s.done:
                    break

        x_est, y_est, theta_est = s.localizer.pose
        traj_lines[i].set_data(s.traj_x, s.traj_y)
        robot_dots[i].set_data([x_est], [y_est])
        ddx = cos(theta_est) * 0.5
        ddy = sin(theta_est) * 0.5
        robot_dirs[i].set_data([x_est, x_est + ddx], [y_est, y_est + ddy])

        # Wall marker (dynamic sim only)
        wx, wy = s.wall_xy
        if wx is not None:
            wall_dots[i].set_data([wx], [wy])
            wall_dots[i].set_alpha(1.0)

        gx, gy = s.goal_xy
        dist = np.hypot(x_est - gx, y_est - gy)
        t    = s.data.time

        if s.success:
            status_texts[i].set_text(f"GOAL  {t:.0f}s")
            status_texts[i].get_bbox_patch().set_facecolor("#0a2a0a")
            robot_dots[i].set_color("#66bb6a")
            robot_dirs[i].set_color("#66bb6a")
        elif s.done:
            status_texts[i].set_text("TIMEOUT")
            status_texts[i].get_bbox_patch().set_facecolor("#2a0a0a")
            robot_dots[i].set_color("#888888")
        else:
            waiting = (s.ob_state == "WAITING")
            if waiting:
                status_texts[i].set_text(f"t={t:.0f}s  STOPPED (waits={s.ob_waits})")
                status_texts[i].get_bbox_patch().set_facecolor("#2a1500")
            else:
                status_texts[i].set_text(f"t={t:.0f}s  d={dist:.1f}m")
                status_texts[i].get_bbox_patch().set_facecolor("#000000")

    return traj_lines + robot_dots + robot_dirs + status_texts + wall_dots


def frame_gen():
    f = 0
    while not all(s.done for s in sims):
        yield f; f += 1
    yield f


print("Rendering ... (this may take a minute)")
anim = animation.FuncAnimation(
    fig, animate,
    frames=frame_gen(),
    interval=1000 / VIDEO_FPS,
    blit=False,
    cache_frame_data=False,
)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
writer = animation.FFMpegWriter(
    fps=VIDEO_FPS, bitrate=4000,
    extra_args=["-vcodec", "libx264", "-pix_fmt", "yuv420p", "-crf", "20"],
)
anim.save(str(OUT_PATH), writer=writer, dpi=100,
          progress_callback=lambda i, n: print(f"  frame {i}", end="\r"))

print(f"\nSaved: {OUT_PATH}")
