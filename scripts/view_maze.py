"""
Instrumented maze viewer for Phase 2 visual inspection.

Builds seed N maze + G1 with:
  - 16-ray 270° LiDAR ring (red cylinders) on torso_link
  - Forward RGB-D camera (blue box) on torso_link
  - G1 placed at maze start cell in keyframe "stand" pose

Usage:
    python scripts/view_maze.py --seed 42
    python scripts/view_maze.py --seed 42 --grid-size 8

Viewer controls (MuJoCo):
    Left-drag   : rotate  |  Right-drag : pan  |  Scroll : zoom
    Space       : pause / resume simulation
    0-9         : switch cameras  (0 = free, 1 = nav_camera)
    F5          : toggle sensor-site visibility
    Ctrl+G      : toggle geom groups
"""

from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from maze.generator import MazeGrid, MazeScene, DIFFICULTY_PRESETS

G1_SCENE      = ROOT / "robot" / "model" / "g1" / "scene.xml"
N_LIDAR_RAYS  = 16
LIDAR_FOV     = np.deg2rad(270)          # 270° horizontal sweep
LIDAR_CUTOFF  = 10.0                     # metres
LIDAR_HEIGHT  = 0.0                      # local z in torso_link frame
RAY_RADIUS    = 0.006                    # cylinder radius (m) — visual only
RAY_HALF_LEN  = 0.12                     # cylinder half-length (m) — visual only


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_body(body, name: str):
    """BFS through MjsBody tree to find a body by name."""
    if body.name == name:
        return body
    for child in body.bodies:
        result = _find_body(child, name)
        if result is not None:
            return result
    return None


def _pointing_quat(theta: float) -> list:
    """
    Quaternion [w,x,y,z] that rotates the site +z axis to point at
    horizontal angle theta (in torso body frame's xy-plane).

    Derivation: rotate [0,0,1] -> [cos θ, sin θ, 0]
      Rotation axis  = [-sin θ, cos θ, 0]  (normalised cross product)
      Rotation angle = π/2
      q = [cos(π/4),  sin(π/4)·(-sin θ),  sin(π/4)·(cos θ),  0]
    """
    s = np.sin(np.pi / 4)   # = cos(π/4) = √2/2
    return [s, -s * np.sin(theta), s * np.cos(theta), 0.0]


def _ray_offset(theta: float, hl: float) -> list:
    """
    Centre the cylinder so its base is at the torso origin.
    Place it at half-length along the ray direction so it spans
    [0, 2·hl] from the torso centre outward.
    """
    return [hl * np.cos(theta), hl * np.sin(theta), LIDAR_HEIGHT]


# ─────────────────────────────────────────────────────────────────────────────
# Scene builder
# ─────────────────────────────────────────────────────────────────────────────

def build_instrumented_scene(seed: int, grid_size: int):
    """
    Compile a full MjModel containing:
      maze walls + G1 + LiDAR sites + camera site + rangefinder sensors.
    """
    # ── 1. Maze grid + base scene (maze walls injected into G1 spec) ──────────
    grid  = MazeGrid(seed=seed, grid_size=grid_size)
    scene = MazeScene(grid, G1_SCENE)
    _model_base, spec = scene.build()

    # ── 2. Find torso_link in the body tree ───────────────────────────────────
    torso = _find_body(spec.worldbody, "torso_link")
    if torso is None:
        raise RuntimeError("torso_link body not found in G1 model spec")
    print(f"  torso_link body found: id={torso.id}")

    # ── 3. LiDAR ring: 16 rangefinder sites on torso ─────────────────────────
    angles = np.linspace(-LIDAR_FOV / 2, LIDAR_FOV / 2, N_LIDAR_RAYS)
    hue_step = 1.0 / N_LIDAR_RAYS

    for i, theta in enumerate(angles):
        site       = torso.add_site()
        site.name  = f"lidar_site_{i:02d}"
        site.type  = mujoco.mjtGeom.mjGEOM_CYLINDER
        site.size  = [RAY_RADIUS, RAY_RADIUS, RAY_HALF_LEN]
        site.pos   = _ray_offset(theta, RAY_HALF_LEN)
        site.quat  = _pointing_quat(theta)
        # Colour: gradient from orange-red (front) to dark-red (rear)
        brightness = 0.5 + 0.5 * np.cos(theta)          # bright in front
        site.rgba  = [1.0, 0.3 * brightness, 0.0, 0.85]
        site.group = 4   # sensor group — toggle with Ctrl+G in viewer

    print(f"  Added {N_LIDAR_RAYS} LiDAR sites  "
          f"(270 deg sweep, cutoff {LIDAR_CUTOFF:.1f} m)")

    # ── 4. Rangefinder sensors for each site ──────────────────────────────────
    for i in range(N_LIDAR_RAYS):
        sensor          = spec.add_sensor()
        sensor.name     = f"lidar_{i:02d}"
        sensor.type     = mujoco.mjtSensor.mjSENS_RANGEFINDER
        sensor.objtype  = mujoco.mjtObj.mjOBJ_SITE
        sensor.objname  = f"lidar_site_{i:02d}"
        sensor.cutoff   = LIDAR_CUTOFF

    # ── 5. Camera site: visual indicator (blue box, front of torso) ───────────
    cam_vis       = torso.add_site()
    cam_vis.name  = "camera_body_vis"
    cam_vis.type  = mujoco.mjtGeom.mjGEOM_BOX
    cam_vis.size  = [0.042, 0.068, 0.024]   # rough RGBD camera dimensions
    cam_vis.pos   = [0.13, 0.0, 0.07]       # front-centre of torso
    cam_vis.quat  = [1.0, 0.0, 0.0, 0.0]
    cam_vis.rgba  = [0.05, 0.25, 0.90, 0.95]
    cam_vis.group = 4

    # Lens circle (dark sphere at camera centre)
    lens       = torso.add_site()
    lens.name  = "camera_lens_vis"
    lens.type  = mujoco.mjtGeom.mjGEOM_SPHERE
    lens.size  = [0.018, 0.018, 0.018]
    lens.pos   = [0.156, 0.0, 0.07]
    lens.rgba  = [0.05, 0.05, 0.05, 1.0]
    lens.group = 4

    print("  Added camera visual indicator (blue box + lens, front of torso)")

    # ── 6. Actual MuJoCo camera (for rendering from robot's POV) ─────────────
    #   Camera looks along its -z axis in MuJoCo convention.
    #   Rotate so -z points along torso +x (robot forward):
    #     rotate +90° around y-axis  => z maps to -x  => camera looks along +x
    cam          = torso.add_camera()
    cam.name     = "nav_camera"
    cam.pos      = [0.16, 0.0, 0.07]
    cam.fovy     = 60.0
    # quat: 90° around +y  => [cos45, 0, sin45, 0] = [0.7071, 0, 0.7071, 0]
    cam.quat     = [0.7071, 0.0, 0.7071, 0.0]
    cam.resolution = [640, 480]

    print("  Added nav_camera  (fovy=60, 640x480, forward-facing)")

    # ── 7. Compile ────────────────────────────────────────────────────────────
    model = spec.compile()
    print(f"  Compiled: nq={model.nq}  nsensor={model.nsensor}  "
          f"ncam={model.ncam}  ngeom={model.ngeom}")

    return model, grid


# ─────────────────────────────────────────────────────────────────────────────
# Position robot at start cell in standing pose
# ─────────────────────────────────────────────────────────────────────────────

def reset_to_start(model, data, grid: MazeGrid):
    """
    Apply keyframe 0 ("stand"), then move the pelvis to the maze start cell.
    The start cell is at world (0, 0) by convention, so only z and q matter.
    """
    mujoco.mj_resetDataKeyframe(model, data, 0)   # applies qpos from "stand" key
    # Keyframe sets pelvis z=0.79, but x and y are whatever —
    # we force x=0, y=0 = maze start cell centre (world origin)
    data.qpos[0] = 0.0   # x
    data.qpos[1] = 0.0   # y
    # z and quaternion come from the keyframe (0.79 m, identity)
    mujoco.mj_forward(model, data)   # propagate kinematics


# ─────────────────────────────────────────────────────────────────────────────
# Post-build diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def print_diagnostics(model, data):
    """Print sensor values and torso world position for verification."""
    torso_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso_link")
    tx, ty, tz = data.xpos[torso_id]
    print(f"\n  torso_link world pos: ({tx:.3f}, {ty:.3f}, {tz:.3f}) m")
    print(f"  (G1 pelvis at z={data.qpos[2]:.3f} m)")

    print(f"\n  LiDAR sensor initial readings (m):")
    for i in range(N_LIDAR_RAYS):
        sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR, f"lidar_{i:02d}")
        adr = model.sensor_adr[sid]
        val = data.sensordata[adr]
        ang = np.rad2deg(np.linspace(-LIDAR_FOV/2, LIDAR_FOV/2, N_LIDAR_RAYS)[i])
        print(f"    lidar_{i:02d}  angle={ang:+7.1f}°  range={val:.3f} m")

    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "nav_camera")
    print(f"\n  nav_camera id: {cam_id}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Instrumented maze viewer")
    parser.add_argument("--seed",      type=int, default=42)
    parser.add_argument("--grid-size", type=int, default=10)
    parser.add_argument("--no-viewer", action="store_true",
                        help="Print diagnostics only, skip GUI")
    args = parser.parse_args()

    print(f"\n=== Building instrumented scene  seed={args.seed}  "
          f"grid={args.grid_size}x{args.grid_size} ===\n")

    model, grid = build_instrumented_scene(args.seed, args.grid_size)
    data        = mujoco.MjData(model)
    reset_to_start(model, data, grid)
    print_diagnostics(model, data)

    if args.no_viewer:
        print("\nSkipping viewer (--no-viewer).")
        return

    print("\n=== Opening viewer ===")
    print("  Controls: left-drag=rotate  right-drag=pan  scroll=zoom")
    print("  Press Space to pause/resume  |  0=free cam  1=nav_camera")
    print("  Press V to toggle sensor sites  |  close window to exit\n")

    with mujoco.viewer.launch_passive(model, data) as viewer:
        # ── Viewer options ────────────────────────────────────────────────────
        viewer.opt.geomgroup[4] = True    # show LiDAR cylinder + camera box
        viewer.opt.sitegroup[4] = True    # show site frames
        viewer.opt.frame = mujoco.mjtFrame.mjFRAME_SITE   # draw site axes

        # ── Initial camera: zoomed in on robot at maze start (world origin) ────
        viewer.cam.type      = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.azimuth   = 45         # look from south-west corner
        viewer.cam.elevation = -25        # slightly above horizontal
        viewer.cam.distance  = 4.5        # close enough to see the robot clearly
        viewer.cam.lookat[0] = 0.0        # robot x (maze start = world origin)
        viewer.cam.lookat[1] = 0.0        # robot y
        viewer.cam.lookat[2] = 0.85       # robot torso height

        # ── Step loop: batch 8 physics steps per viewer sync (≈ real-time) ───
        # On Windows time.sleep(0.002) has ~15 ms resolution, so we sleep
        # once per batch of 8 steps × 2 ms = 16 ms ≈ one Windows tick.
        SYNC_HZ        = 60
        steps_per_sync = max(1, int(round(1.0 / (model.opt.timestep * SYNC_HZ))))
        sleep_s        = 1.0 / SYNC_HZ

        last_print = 0.0
        print(f"  Simulation running — steps_per_sync={steps_per_sync}  "
              f"target={SYNC_HZ} Hz sync")

        while viewer.is_running():
            for _ in range(steps_per_sync):
                mujoco.mj_step(model, data)
            viewer.sync()
            time.sleep(sleep_s)

            # Print live LiDAR readings every 2 seconds
            if data.time - last_print >= 2.0:
                last_print = data.time
                torso_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_BODY, "torso_link")
                tz = data.xpos[torso_id][2]
                readings = [
                    data.sensordata[model.sensor_adr[
                        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR,
                                          f"lidar_{i:02d}")]]
                    for i in range(N_LIDAR_RAYS)
                ]
                valid = [r for r in readings if r > 0.05]   # exclude self-hits
                min_r = min(valid) if valid else float("nan")
                max_r = max(valid) if valid else float("nan")
                print(f"  t={data.time:6.2f}s  torso_z={tz:.3f}m  "
                      f"lidar_min={min_r:.2f}m  lidar_max={max_r:.2f}m")

    print("Viewer closed.")


if __name__ == "__main__":
    main()
