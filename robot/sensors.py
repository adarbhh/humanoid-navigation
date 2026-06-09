"""
Sensor extraction from mujoco.Data.

All functions take (model, data) and return numpy arrays with documented shapes.
Timestamps are always sim_time = data.time (float, seconds).
"""

from __future__ import annotations
import numpy as np


# ── IMU ───────────────────────────────────────────────────────────────────────

def get_imu(model, data) -> dict:
    """
    Returns accelerometer + gyroscope readings from torso IMU.
    Sensor names from MuJoCo Menagerie G1 model:
      imu-torso-angular-velocity   (gyro,  3-axis)
      imu-torso-linear-acceleration (accel, 3-axis)
    """
    acc  = _sensor_by_name(model, data, "imu-torso-linear-acceleration", shape=(3,))
    gyro = _sensor_by_name(model, data, "imu-torso-angular-velocity",    shape=(3,))
    return {
        "time":  data.time,
        "accel": acc,    # m/s²  shape (3,)
        "gyro":  gyro,   # rad/s shape (3,)
    }


# ── Joint state ───────────────────────────────────────────────────────────────

def get_joint_state(model, data) -> dict:
    """Full joint position / velocity / torque for all DoFs."""
    return {
        "time":  data.time,
        "qpos":  data.qpos.copy(),   # (nq,)
        "qvel":  data.qvel.copy(),   # (nv,)
        "ctrl":  data.ctrl.copy(),   # (nu,)  commanded torques/positions
        "qfrc":  data.qfrc_actuator.copy(),  # (nv,) actual torques
    }


# ── Base state (ground-truth pose — scoring only) ─────────────────────────────

def get_gt_pose(model, data) -> dict:
    """
    Ground-truth 6-DoF pose of the pelvis body.
    MUST NOT be fed into the navigation stack — scoring use only.
    """
    body_id = _body_id(model, "pelvis")
    pos  = data.xpos[body_id].copy()   # (3,)  world xyz
    quat = data.xquat[body_id].copy()  # (4,)  w x y z
    vel  = data.cvel[body_id].copy()   # (6,)  spatial velocity
    return {
        "time": data.time,
        "pos":  pos,
        "quat": quat,
        "vel":  vel,
    }


# ── LiDAR (rangefinder array) ─────────────────────────────────────────────────

def get_lidar(model, data, prefix: str = "lidar") -> dict:
    """
    Reads all rangefinder sensors whose names start with `prefix`.
    Returns ranges (m) and the angle of each ray.
    Sensors must be added to the G1 XML by our setup code.
    """
    import mujoco
    ranges = []
    for i in range(model.nsensor):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_SENSOR, i)
        if name and name.startswith(prefix):
            sensor_adr = model.sensor_adr[i]
            ranges.append(data.sensordata[sensor_adr])
    ranges = np.array(ranges, dtype=np.float32)
    n = len(ranges)
    angles = np.linspace(-np.pi * 0.75, np.pi * 0.75, n) if n > 0 else np.array([])
    return {
        "time":   data.time,
        "ranges": ranges,   # (n_rays,)  meters, inf = no hit
        "angles": angles,   # (n_rays,)  radians
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _body_id(model, name: str) -> int:
    import mujoco
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    if bid < 0:
        # Fall back to body 1 (first non-world body)
        return 1
    return bid


def _sensor_by_name(model, data, name: str, shape: tuple) -> np.ndarray:
    import mujoco
    sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR, name)
    if sid < 0:
        return np.zeros(shape, dtype=np.float32)
    adr = model.sensor_adr[sid]
    dim = int(np.prod(shape))
    return data.sensordata[adr : adr + dim].copy().astype(np.float32)
