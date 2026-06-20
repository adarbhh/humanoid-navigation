"""
Generate report/grid_demo.mp4
3×4 grid of 12 maze runs playing simultaneously at 2x speed.

Usage:
    conda run -n robotics-assignment python make_grid_demo.py
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

# Point matplotlib's FFMpegWriter at the bundled binary
matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
sys.path.insert(0, str(ROOT))

from maze.generator import MazeGrid, MazeScene
from robot.sensors  import get_lidar, get_imu
from robot.walking_policy.interface import WalkingPolicyInterface
from navigation.occupancy_grid import OccupancyGrid
from navigation.localization   import Localizer
from navigation.controller     import PurePursuitController

# ── Config ────────────────────────────────────────────────────────────────────
import json as _json
_batch = _json.load(open(ROOT / "runs" / "batch_results.json"))
SEEDS = [r["seed"] for r in _batch][:12]   # first 12 from batch

GRID_ROWS       = 3
GRID_COLS       = 4
CELL_PX         = 260          # pixel size of each cell (square)
VIDEO_FPS       = 10
TICKS_PER_FRAME = 8            # 8 × (1/20 Hz) × 10 FPS = 4× sim speed
MAX_SIM_TIME    = 300.0        # seconds; robot is timed out after this
CONTROL_HZ      = 20
INFLATE_R       = 3
N_LIDAR         = 16
LIDAR_FOV       = np.deg2rad(270)
LIDAR_CUTOFF    = 10.0

G1_SCENE = ROOT / "robot" / "model" / "g1" / "scene.xml"
OUT_PATH  = ROOT / "report" / "grid_demo.mp4"

DT = 1.0 / CONTROL_HZ


# ── Minimal scene builder (same as runner.py) ─────────────────────────────────
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


def build_scene(seed: int, grid_size: int = 10):
    grid  = MazeGrid(seed=seed, grid_size=grid_size)
    scene = MazeScene(grid, G1_SCENE)
    _, spec = scene.build()

    torso = _find_body(spec.worldbody, "torso_link")
    if torso is None:
        raise RuntimeError("torso_link not found")

    angles = np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR)
    hl = 0.12
    for i, theta in enumerate(angles):
        site       = torso.add_site()
        site.name  = f"lidar_site_{i:02d}"
        site.type  = mujoco.mjtGeom.mjGEOM_CYLINDER
        site.size  = [0.006, 0.006, hl]
        site.pos   = [hl * np.cos(theta), hl * np.sin(theta), 0.0]
        site.quat  = _pointing_quat(theta)
        site.rgba  = [1.0, 0.3, 0.0, 0.6]
        site.group = 4

    for i in range(N_LIDAR):
        sensor         = spec.add_sensor()
        sensor.name    = f"lidar_{i:02d}"
        sensor.type    = mujoco.mjtSensor.mjSENS_RANGEFINDER
        sensor.objtype = mujoco.mjtObj.mjOBJ_SITE
        sensor.objname = f"lidar_site_{i:02d}"
        sensor.cutoff  = LIDAR_CUTOFF

    model = spec.compile()
    data  = mujoco.MjData(model)
    return model, data, grid


# ── Per-simulation state ──────────────────────────────────────────────────────
@dataclass
class Sim:
    seed:         int
    model:        object
    data:         object
    policy:       object
    localizer:    object
    controller:   object
    occ_nav:      object
    lidar_angles: np.ndarray
    goal_xy:      tuple
    path:         list
    traj_x: list  = field(default_factory=list)
    traj_y: list  = field(default_factory=list)
    last_yaw: float = 0.0
    prev_x:   float = 0.0
    prev_y:   float = 0.0
    done:     bool  = False
    success:  bool  = False


def _occupied(occ_nav, px, py) -> bool:
    r, c = occ_nav.world_to_cell(px, py)
    return not occ_nav.in_bounds(r, c) or occ_nav.grid[r, c] == OccupancyGrid.OCCUPIED


def step(s: Sim) -> None:
    """Advance one control tick (DT seconds)."""
    if s.done:
        return

    cur_x = float(s.data.qpos[0])
    cur_y = float(s.data.qpos[1])

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

    vx, vy, yaw_rate = s.controller.step(
        x_est, y_est, theta_est,
        lidar_ranges=lidar["ranges"],
        lidar_angles=s.lidar_angles,
    )

    s.policy.set_command(vx, vy, yaw_rate)
    s.policy.step(s.model, s.data, dt=DT)

    # Collision resolution
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


# ── Build all 12 simulations ──────────────────────────────────────────────────
print("Building 12 simulations ...")
sims: list[Sim] = []

for seed in SEEDS:
    print(f"  seed {seed:>5} ...", end="", flush=True)
    model, data, maze_grid = build_scene(seed)

    occ_raw = OccupancyGrid(resolution=0.1, x_min=-1, x_max=16, y_min=-1, y_max=16)
    occ_raw.load_from_maze(maze_grid)
    occ_nav = occ_raw.inflated(INFLATE_R)

    path    = [(float(x), float(y)) for x, y in maze_grid.solution_world_xy()]
    goal_xy = maze_grid.cell_centre_world(*maze_grid.goal_cell)

    theta0 = 0.0
    if len(path) >= 2:
        ddx = path[1][0] - path[0][0]
        ddy = path[1][1] - path[0][1]
        theta0 = float(np.arctan2(ddy, ddx))

    mujoco.mj_resetDataKeyframe(model, data, 0)
    data.qpos[0], data.qpos[1] = 0.0, 0.0
    data.qpos[3] = np.cos(theta0 / 2)
    data.qpos[4] = 0.0
    data.qpos[5] = 0.0
    data.qpos[6] = np.sin(theta0 / 2)
    mujoco.mj_forward(model, data)

    policy     = WalkingPolicyInterface(model, backend="kinematic")
    localizer  = Localizer(x0=0.0, y0=0.0, theta0=theta0, rng_seed=seed)
    controller = PurePursuitController(lookahead=0.6, max_vx=0.35,
                                       max_yaw=1.5, goal_tol=0.35)
    controller.set_path(path)

    sims.append(Sim(
        seed=seed, model=model, data=data,
        policy=policy, localizer=localizer, controller=controller,
        occ_nav=occ_nav,
        lidar_angles=np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR),
        goal_xy=goal_xy, path=path,
    ))
    print(" ok")


# ── Build figure ──────────────────────────────────────────────────────────────
print("Building figure ...")

MAZE_CMAP = LinearSegmentedColormap.from_list(
    "maze", ["#ffffff", "#111111"], N=256   # white open, dark walls
)

fig_w = CELL_PX * GRID_COLS / 100
fig_h = CELL_PX * GRID_ROWS / 100
fig, axes = plt.subplots(GRID_ROWS, GRID_COLS,
                         figsize=(fig_w, fig_h), dpi=100)
fig.patch.set_facecolor("#000000")
plt.subplots_adjust(left=0.002, right=0.998, top=0.998, bottom=0.002,
                    wspace=0.015, hspace=0.015)

traj_lines:   list = []
robot_dots:   list = []
robot_dirs:   list = []
status_texts: list = []
seed_labels:  list = []

for s, ax in zip(sims, axes.flat):
    ax.set_facecolor("#000000")

    occ    = s.occ_nav
    extent = [occ.x_min, occ.x_min + occ.W * occ.res,
              occ.y_min, occ.y_min + occ.H * occ.res]
    ax.imshow(occ.grid, origin="lower", extent=extent,
              cmap=MAZE_CMAP, vmin=0, vmax=100, aspect="equal")

    if len(s.path) >= 2:
        px, py = zip(*s.path)
        ax.plot(px, py, color="#4fc3f7", lw=2.5, alpha=0.9, zorder=2)

    gx, gy = s.goal_xy
    ax.scatter([gx], [gy], c="#ffd54f", s=55, marker="*", zorder=4)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.axis("off")

    # Dynamic artists
    tl,   = ax.plot([], [], ".", color="#66bb6a",
                    markersize=1.5, alpha=0.45, zorder=3)
    rd,   = ax.plot([], [], "o", color="#ef5350",
                    markersize=5, zorder=5)
    rdir, = ax.plot([], [], "-", color="#ef5350",
                    lw=1.8, zorder=5)

    # Seed badge (top-left)
    sl = ax.text(0.03, 0.97, f"seed {s.seed}",
                 transform=ax.transAxes, fontsize=6.5,
                 va="top", color="#ffffff", fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.25",
                           facecolor="#000000", alpha=0.82),
                 zorder=6)

    # Status badge (bottom-left)
    st = ax.text(0.03, 0.04, "", transform=ax.transAxes, fontsize=6,
                 va="bottom", color="#ffffff",
                 bbox=dict(boxstyle="round,pad=0.25",
                           facecolor="#000000", alpha=0.78),
                 zorder=6)

    traj_lines.append(tl)
    robot_dots.append(rd)
    robot_dirs.append(rdir)
    seed_labels.append(sl)
    status_texts.append(st)


# ── Animation ─────────────────────────────────────────────────────────────────
def animate(frame: int):
    active = 0
    for i, s in enumerate(sims):
        if not s.done:
            for _ in range(TICKS_PER_FRAME):
                step(s)
                if s.done:
                    break
            active += 1

        x_est, y_est, theta_est = s.localizer.pose
        traj_lines[i].set_data(s.traj_x, s.traj_y)
        robot_dots[i].set_data([x_est], [y_est])
        ddx = cos(theta_est) * 0.45
        ddy = sin(theta_est) * 0.45
        robot_dirs[i].set_data([x_est, x_est + ddx], [y_est, y_est + ddy])

        gx, gy = s.goal_xy
        dist   = np.hypot(x_est - gx, y_est - gy)
        t      = s.data.time

        if s.success:
            status_texts[i].set_text(f"DONE  {t:.0f}s")
            status_texts[i].get_bbox_patch().set_facecolor("#0a2a0a")
            robot_dots[i].set_color("#66bb6a")
            robot_dirs[i].set_color("#66bb6a")
        elif s.done:
            status_texts[i].set_text("TIMEOUT")
            status_texts[i].get_bbox_patch().set_facecolor("#2a0a0a")
            robot_dots[i].set_color("#888888")
            robot_dirs[i].set_color("#888888")
        else:
            status_texts[i].set_text(f"t={t:.0f}s  d={dist:.1f}m")

    return traj_lines + robot_dots + robot_dirs + status_texts


def frame_gen():
    """Yield frame indices; stop once every sim is finished."""
    f = 0
    while not all(s.done for s in sims):
        yield f
        f += 1
    # One final frame so the finished state is visible
    yield f


print("Rendering ... (this may take a few minutes)")
anim = animation.FuncAnimation(
    fig, animate,
    frames=frame_gen(),
    interval=1000 / VIDEO_FPS,
    blit=False,
    cache_frame_data=False,
)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
writer = animation.FFMpegWriter(
    fps=VIDEO_FPS, bitrate=3000,
    extra_args=["-vcodec", "libx264", "-pix_fmt", "yuv420p", "-crf", "22"],
)
anim.save(str(OUT_PATH), writer=writer, dpi=100,
          progress_callback=lambda i, n: print(f"  frame {i}", end="\r"))

print(f"\nSaved: {OUT_PATH}")
