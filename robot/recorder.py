"""
Crash-safe multi-rate HDF5 data recorder for G1 maze navigation runs.

Schema
------
run_seed<SEED>_<TIMESTAMP>.h5
│
├── (file attrs)
│     schema_version       str    "1.0"
│     seed                 int
│     grid_size            int
│     recording_complete   bool   False until clean close; detects truncation
│     elapsed_s            float  wall-clock run duration
│     target_hz_<stream>   float  one per stream
│     actual_hz_<stream>   float  one per stream, written at close
│
├── meta/                         static episode metadata
│     start_world  (2,) float32   maze start position [x, y] metres
│     goal_world   (2,) float32   maze goal  position [x, y] metres
│
├── path/                         planned trajectory (written once before episode)
│     waypoints    (N, 2) float32  world-frame (x, y) corridor-centre waypoints
│     occ_nav      (H, W) uint8    inflated GT occupancy grid used for planning
│                                  (FREE=0, OCCUPIED=100, UNKNOWN=50)
│
├── imu/                          target 20 Hz  (kinematic sim: matches control rate)
│     time   (N,)    float64       data.time seconds
│     gyro   (N, 3)  float32       rad/s  [x, y, z]  (imu-torso-angular-velocity)
│     accel  (N, 3)  float32       m/s²   [x, y, z]  (imu-torso-linear-acceleration)
│
├── base_state/                   target 20 Hz
│     time       (N,)  float64     data.time seconds
│     est_x      (N,)  float32     dead-reckoning estimated x (m)
│     est_y      (N,)  float32     dead-reckoning estimated y (m)
│     est_theta  (N,)  float32     dead-reckoning estimated heading (rad)
│     vx_cmd     (N,)  float32     forward velocity command  (m/s)
│     vy_cmd     (N,)  float32     lateral velocity command  (m/s)  always 0
│     yaw_rate   (N,)  float32     yaw-rate command          (rad/s)
│
├── joint_state/                  target 20 Hz
│     time  (N,)       float64     data.time seconds
│     qpos  (N, nq)    float32     full joint-position vector
│     qvel  (N, nv)    float32     full joint-velocity vector
│
├── lidar/                        target 20 Hz
│     time    (N,)      float64    data.time seconds
│     ranges  (N, 16)   float32    rangefinder distances (m); LIDAR_CUTOFF = no hit
│
├── camera/                       target 10 Hz  (every 2nd control tick)
│     time   (N,)               float64   data.time seconds
│     rgb    (N, H, W, 3)       uint8     head camera BGR image  (H=120, W=160)
│     depth  (N, H, W)          float32   raw MuJoCo depth buffer [0, 1] clip-space
│                                         → metres: near*far / (far - d*(far-near))
│                                         where near = znear*extent, far = zfar*extent
│
└── gt_pose/                      target 20 Hz   *** SCORING USE ONLY ***
      time  (N,)   float64         data.time seconds
      pos   (N, 3) float32         pelvis world-frame position   [x, y, z]  (m)
      quat  (N, 4) float32         pelvis world-frame quaternion [w, x, y, z]

Crash safety
------------
A background thread drains a queue and batches rows to HDF5 datasets, then
calls h5py.File.flush() + os.fsync() every FLUSH_INTERVAL seconds.  Between
fsyncs, at most FLUSH_INTERVAL * rate samples are in memory only; the file is
always structurally valid on disk.  A kill -9 loses at most those in-flight
samples — the dataset is never corrupted.  The `recording_complete` attribute
is written only on clean close(), so a truncated file is detectable.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Optional

import h5py
import numpy as np

# Only imported when camera rendering is requested
_mujoco = None

FLUSH_INTERVAL  = 0.5   # seconds between forced fsyncs
SCHEMA_VERSION  = "1.0"
_PASS_THRESHOLD = 0.80  # achieved_hz / target_hz must exceed this to PASS

# Per-stream: target_hz, HDF5 chunk rows
_STREAM_CFG: dict[str, dict] = {
    "imu":         {"hz": 20, "chunk": 64},
    "base_state":  {"hz": 20, "chunk": 64},
    "joint_state": {"hz": 20, "chunk": 32},
    "lidar":       {"hz": 20, "chunk": 64},
    "camera":      {"hz": 10, "chunk":  4},
    "gt_pose":     {"hz": 20, "chunk": 64},
}


class Recorder:
    """
    Multi-stream HDF5 recorder with background write thread.

    Thread model
    ------------
    Main thread  : calls record_*() → enqueues lightweight items (timestamps +
                   small numpy arrays).  record_camera() only snapshots qpos —
                   no GL call on the critical path.
    Writer thread: drains the queue, writes HDF5, AND does camera rendering
                   with its own Renderer + MjData context.  GL is always called
                   from the same thread that owns the context.

    Rate measurement
    ----------------
    Rates are reported in simulation-Hz (samples per sim-second elapsed) so
    they are correct regardless of whether the sim runs in real-time or faster.
    """

    # Sentinel key for camera-render requests
    _CAM_SNAP = "__cam_snap__"

    def __init__(
        self,
        model,                      # mujoco.MjModel
        seed:       int,
        grid_size:  int,
        out_dir:    str  = "runs",
        cam_height: int  = 120,
        cam_width:  int  = 160,
    ) -> None:
        global _mujoco
        import mujoco as _mj
        _mujoco = _mj

        self._model    = model
        self._cam_h    = cam_height
        self._cam_w    = cam_width

        # Find camera id; disable camera recording if absent
        cam_id = _mujoco.mj_name2id(
            model, _mujoco.mjtObj.mjOBJ_CAMERA, "nav_camera"
        )
        self._cam_id = cam_id if cam_id >= 0 else None

        # Per-stream sample counters + sim-time range for rate measurement
        self._counters:   dict[str, int]   = {k: 0   for k in _STREAM_CFG}
        self._first_t:    dict[str, float] = {k: None for k in _STREAM_CFG}
        self._last_t:     dict[str, float] = {k: None for k in _STREAM_CFG}
        self._t_start = time.perf_counter()

        # Create output file
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._path = out_path / f"run_seed{seed:04d}_{ts}.h5"

        self._file = h5py.File(self._path, "w")
        self._datasets: dict[str, h5py.Dataset] = {}
        # Lock serialises ALL h5py calls across main thread and writer thread.
        # h5py is not thread-safe without the GIL being held continuously, so
        # we use an explicit lock rather than relying on CPython's GIL.
        self._file_lock: threading.Lock = threading.Lock()
        self._init_schema(seed, grid_size, model.nq, model.nv)

        # Background writer — also owns the camera renderer (GL context lives here)
        self._queue:        queue.Queue     = queue.Queue()
        self._stop_event:   threading.Event = threading.Event()
        self._writer_error: Optional[Exception] = None
        self._writer = threading.Thread(
            target=self._writer_loop, daemon=True, name="hdf5-writer"
        )
        self._writer.start()

        print(f"[Recorder] {self._path.name}  "
              f"(cam={'on' if self._cam_id is not None else 'off'})")

    # ── Schema initialisation ─────────────────────────────────────────────────

    def _init_schema(self, seed: int, grid_size: int, nq: int, nv: int) -> None:
        f = self._file

        f.attrs["schema_version"]   = SCHEMA_VERSION
        f.attrs["seed"]             = seed
        f.attrs["grid_size"]        = grid_size
        f.attrs["recording_complete"] = False

        for stream, cfg in _STREAM_CFG.items():
            f.attrs[f"target_hz_{stream}"] = float(cfg["hz"])

        f.create_group("meta")
        f.create_group("path")

        gt = f.create_group("gt_pose")
        gt.attrs["note"] = "SCORING USE ONLY — never feed into the navigation stack"

        # Helper: create a resizable chunked dataset
        def ds(path: str, shape: tuple, dtype, chunk_rows: int) -> None:
            full_shape = (0,)  + shape
            max_shape  = (None,) + shape
            chunks     = (chunk_rows,) + shape
            # lzf: bundled with h5py, fast compression, good for floats/ints
            compr = "lzf" if path.startswith("camera/") else None
            d = f.create_dataset(
                path,
                shape=full_shape, maxshape=max_shape,
                dtype=dtype, chunks=chunks,
                compression=compr,
            )
            self._datasets[path] = d

        c = lambda s: _STREAM_CFG[s]["chunk"]

        ds("imu/time",           (), np.float64, c("imu"))
        ds("imu/gyro",        (3,), np.float32, c("imu"))
        ds("imu/accel",       (3,), np.float32, c("imu"))

        ds("base_state/time",        (),  np.float64, c("base_state"))
        ds("base_state/est_x",       (),  np.float32, c("base_state"))
        ds("base_state/est_y",       (),  np.float32, c("base_state"))
        ds("base_state/est_theta",   (),  np.float32, c("base_state"))
        ds("base_state/vx_cmd",      (),  np.float32, c("base_state"))
        ds("base_state/vy_cmd",      (),  np.float32, c("base_state"))
        ds("base_state/yaw_rate",    (),  np.float32, c("base_state"))

        ds("joint_state/time", (),              np.float64, c("joint_state"))
        ds("joint_state/qpos", (max(1, nq),),  np.float32, c("joint_state"))
        ds("joint_state/qvel", (max(1, nv),),  np.float32, c("joint_state"))

        ds("lidar/time",    (),     np.float64, c("lidar"))
        ds("lidar/ranges",  (16,),  np.float32, c("lidar"))

        ds("camera/time",  (),                          np.float64, c("camera"))
        ds("camera/rgb",   (self._cam_h, self._cam_w, 3), np.uint8,   c("camera"))
        ds("camera/depth", (self._cam_h, self._cam_w),    np.float32, c("camera"))

        ds("gt_pose/time", (),    np.float64, c("gt_pose"))
        ds("gt_pose/pos",  (3,),  np.float32, c("gt_pose"))
        ds("gt_pose/quat", (4,),  np.float32, c("gt_pose"))

        f.flush()

    # ── Static metadata ───────────────────────────────────────────────────────

    def record_meta(
        self,
        start_xy:  tuple[float, float],
        goal_xy:   tuple[float, float],
        waypoints: list[tuple[float, float]],
        occ_nav,
    ) -> None:
        """Write episode metadata once before the run starts."""
        with self._file_lock:
            f = self._file
            f["meta"].attrs["start_world"] = np.array(start_xy, np.float32)
            f["meta"].attrs["goal_world"]  = np.array(goal_xy,  np.float32)
            f["path"].create_dataset(
                "waypoints", data=np.array(waypoints, np.float32)
            )
            f["path"].create_dataset("occ_nav", data=occ_nav.grid)
            f.flush()

    # ── Per-tick record methods (called from main thread) ─────────────────────

    def record_imu(self, t: float, gyro: np.ndarray, accel: np.ndarray) -> None:
        self._put("imu/time",  np.float64(t))
        self._put("imu/gyro",  gyro.astype(np.float32))
        self._put("imu/accel", accel.astype(np.float32))
        self._counters["imu"] += 1
        self._track_t("imu", t)

    def record_base(
        self, t: float,
        x: float, y: float, theta: float,
        vx: float, vy: float, yaw_rate: float,
    ) -> None:
        self._put("base_state/time",      np.float64(t))
        self._put("base_state/est_x",     np.float32(x))
        self._put("base_state/est_y",     np.float32(y))
        self._put("base_state/est_theta", np.float32(theta))
        self._put("base_state/vx_cmd",    np.float32(vx))
        self._put("base_state/vy_cmd",    np.float32(vy))
        self._put("base_state/yaw_rate",  np.float32(yaw_rate))
        self._counters["base_state"] += 1
        self._track_t("base_state", t)

    def record_joints(self, t: float, qpos: np.ndarray, qvel: np.ndarray) -> None:
        self._put("joint_state/time", np.float64(t))
        self._put("joint_state/qpos", qpos.astype(np.float32))
        self._put("joint_state/qvel", qvel.astype(np.float32))
        self._counters["joint_state"] += 1
        self._track_t("joint_state", t)

    def record_lidar(self, t: float, ranges: np.ndarray) -> None:
        self._put("lidar/time",   np.float64(t))
        self._put("lidar/ranges", ranges.astype(np.float32))
        self._counters["lidar"] += 1
        self._track_t("lidar", t)

    def record_camera(self, t: float, mj_data) -> None:
        """
        Queue a camera snapshot for the background writer thread.

        Only mj_data.qpos is copied here (~1 µs).  The actual GL rendering
        (400 ms on Windows software-GL) runs on the writer thread so the
        control loop is never stalled.
        """
        if self._cam_id is None:
            return
        # Tuple sentinel avoids key collision with HDF5 dataset paths.
        self._queue.put((self._CAM_SNAP, np.float64(t), mj_data.qpos.copy()))
        self._counters["camera"] += 1
        self._track_t("camera", float(t))

    def record_gt(self, t: float, pos: np.ndarray, quat: np.ndarray) -> None:
        """Ground-truth pelvis pose — scoring only, never used for navigation."""
        self._put("gt_pose/time", np.float64(t))
        self._put("gt_pose/pos",  pos.astype(np.float32))
        self._put("gt_pose/quat", quat.astype(np.float32))
        self._counters["gt_pose"] += 1
        self._track_t("gt_pose", t)

    # ── Sim-time tracking helper ──────────────────────────────────────────────

    def _track_t(self, stream: str, t: float) -> None:
        """Record the first and last simulation timestamp seen for a stream."""
        if self._first_t[stream] is None:
            self._first_t[stream] = t
        self._last_t[stream] = t

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def close(self) -> dict[str, float]:
        """
        Drain the write queue, fsync, stamp completion flag.
        Returns achieved rates per stream.  Prints a pass/fail table.
        """
        self._stop_event.set()
        self._writer.join(timeout=30.0)

        elapsed = max(time.perf_counter() - self._t_start, 1e-3)

        if self._writer_error:
            print(f"[Recorder] WARNING: writer thread had error: {self._writer_error}")

        # Drain any non-camera items the writer thread missed (short runs where
        # the OS never scheduled the writer before stop_event fired).
        # Camera snaps are dropped here — we can't render without the GL context.
        residual: dict[str, list] = {}
        try:
            while True:
                item = self._queue.get_nowait()
                if item[0] is self._CAM_SNAP:
                    continue       # GL context already torn down; skip
                key, val = item
                residual.setdefault(key, []).append(val)
        except queue.Empty:
            pass
        if residual:
            self._write_batch(residual)
        self._fsync()

        # Rate stats — use sim-time elapsed (last_t - first_t per stream) so
        # the rate is correct whether the sim runs in real-time or faster.
        # Wall-time elapsed is kept as a fallback for streams with <2 samples.
        rates: dict[str, float] = {}
        with self._file_lock:
            for stream, cfg in _STREAM_CFG.items():
                n  = self._counters[stream]
                t0 = self._first_t[stream]
                t1 = self._last_t[stream]
                if t0 is not None and t1 is not None and t1 > t0:
                    hz = (n - 1) / (t1 - t0)   # samples per sim-second
                elif elapsed > 0:
                    hz = n / elapsed             # fallback: wall-time
                else:
                    hz = 0.0
                rates[stream] = hz
                self._file.attrs[f"actual_hz_{stream}"] = hz

            self._file.attrs["recording_complete"] = True
            self._file.attrs["elapsed_s"]          = elapsed
            self._file.flush()

        self._file.close()

        # ── Rate report ───────────────────────────────────────────────────────
        print("\n[Recorder] Capture-rate report  (sim-Hz)")
        print(f"  {'stream':<14} {'target':>8}  {'actual':>8}  {'result':>8}")
        print(f"  {'-'*48}")
        all_pass = True
        for stream, cfg in _STREAM_CFG.items():
            target  = float(cfg["hz"])
            actual  = rates[stream]
            ratio   = actual / target if target > 0 else 1.0
            ok      = ratio >= _PASS_THRESHOLD
            label   = "PASS" if ok else "FAIL"
            if not ok:
                all_pass = False
            print(f"  {stream:<14} {target:>6.0f} Hz  "
                  f"{actual:>6.1f} Hz  [{label}] {ratio*100:.0f}%")

        mb = self._path.stat().st_size / 1_048_576
        print(f"\n  File : {self._path}  ({mb:.1f} MB)")
        print(f"  Total: {'ALL PASS' if all_pass else 'SOME STREAMS BELOW 80% TARGET'}\n")

        return rates

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _put(self, key: str, value: np.ndarray) -> None:
        self._queue.put((key, value))

    def _writer_loop(self) -> None:
        """Background thread: drain queue → batch HDF5 appends → periodic fsync."""
        try:
            self._writer_loop_inner()
        except Exception as exc:
            self._writer_error = exc
            import traceback
            print(f"[Recorder] Writer thread crashed: {exc}", flush=True)
            traceback.print_exc()

    def _writer_loop_inner(self) -> None:
        last_fsync  = time.perf_counter()
        # Camera renderer lives on this thread — GL context is thread-local.
        cam_renderer = None
        cam_data     = None  # private MjData for rendering

        try:
            while not self._stop_event.is_set() or not self._queue.empty():
                batch:     dict[str, list]           = {}
                cam_snaps: list[tuple[float, object]] = []  # (t, qpos)

                # Drain all available items
                try:
                    while True:
                        item = self._queue.get_nowait()
                        if item[0] is self._CAM_SNAP:
                            _, t, qpos = item
                            cam_snaps.append((float(t), qpos))
                        else:
                            key, val = item
                            batch.setdefault(key, []).append(val)
                except queue.Empty:
                    pass

                # Write non-camera data first (fast)
                if batch:
                    self._write_batch(batch)

                # Render camera snaps (slow — but off the control-loop thread)
                for t, qpos in cam_snaps:
                    if self._cam_id is None:
                        continue
                    if cam_renderer is None and self._cam_id is not None:
                        try:
                            cam_renderer = _mujoco.Renderer(
                                self._model,
                                height=self._cam_h, width=self._cam_w,
                            )
                            cam_data = _mujoco.MjData(self._model)
                        except Exception as exc:
                            print(f"[Recorder] Camera renderer init failed: {exc}",
                                  flush=True)
                            self._cam_id = None
                            continue
                    try:
                        cam_data.qpos[:] = qpos
                        _mujoco.mj_forward(self._model, cam_data)
                        cam_renderer.update_scene(cam_data, camera=self._cam_id)
                        rgb = cam_renderer.render().copy()
                        cam_renderer.enable_depth_rendering()
                        cam_renderer.update_scene(cam_data, camera=self._cam_id)
                        depth = cam_renderer.render().copy()
                        cam_renderer.disable_depth_rendering()
                    except Exception as exc:
                        print(f"[Recorder] Camera render error: {exc}", flush=True)
                        continue
                    self._write_batch({
                        "camera/time":  [np.float64(t)],
                        "camera/rgb":   [rgb],
                        "camera/depth": [depth],
                    })

                now = time.perf_counter()
                if now - last_fsync >= FLUSH_INTERVAL:
                    self._fsync()
                    last_fsync = now
                elif not batch and not cam_snaps:
                    time.sleep(0.005)

        finally:
            if cam_renderer is not None:
                try:
                    cam_renderer.close()
                except Exception:
                    pass

        # Final sync
        self._fsync()

    def _write_batch(self, batch: dict[str, list]) -> None:
        with self._file_lock:
            for key, values in batch.items():
                ds = self._datasets.get(key)
                if ds is None:
                    continue
                arr   = np.stack(values)           # (n, *sample_shape)
                old_n = ds.shape[0]
                new_n = old_n + len(values)
                ds.resize(new_n, axis=0)
                ds[old_n:new_n] = arr

    def _fsync(self) -> None:
        with self._file_lock:
            try:
                self._file.flush()
                try:
                    fd = self._file.id.get_vfd_handle()
                    os.fsync(fd)
                except Exception:
                    pass  # flush to OS cache is the minimum guarantee
            except Exception:
                pass
