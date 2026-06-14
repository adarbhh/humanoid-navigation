"""
Walking policy interface: translate (vx, vy, yaw_rate) commands into motion.

Backends
--------
kinematic  (default) — directly updates freejoint qpos + calls mj_forward.
           Robot slides without a walking animation but never falls.
           Sufficient to demonstrate and evaluate the navigation stack.
           No torch / RL weights needed.

pd_stub    — PD position controller holds the standing keyframe pose.
           Robot stays upright but cannot translate.  Useful for sensor tests.

rl_policy  — unitree_rl_gym sim2sim checkpoint (Phase 3 extension slot).
           Raises NotImplementedError until weights are provided.
"""

from __future__ import annotations

import numpy as np


class WalkingPolicyInterface:
    KINEMATIC = "kinematic"
    PD_STUB   = "pd_stub"
    RL        = "rl_policy"

    def __init__(self, model, backend: str = "kinematic") -> None:
        self._backend  = backend
        self._cmd_vx   = 0.0
        self._cmd_vy   = 0.0
        self._cmd_yaw  = 0.0
        self._model    = model

        # Snapshot standing pose from keyframe so kinematic mode can restore joints.
        import mujoco
        _data = mujoco.MjData(model)
        mujoco.mj_resetDataKeyframe(model, _data, 0)
        self._stand_z            = float(_data.qpos[2])   # pelvis standing height
        self._stand_qpos_joints  = _data.qpos[7:].copy()  # joint angles
        self._stand_ctrl         = _data.ctrl.copy()       # actuator targets

        # CPG gait state
        self._gait_phase  = 0.0
        self._stride_len  = 0.40   # metres per full gait cycle (both legs)
        self._gait_map    = self._build_gait_map(model)

        if backend == self.RL:
            self._load_rl_policy(model)

    # ── Gait map ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_gait_map(model) -> dict:
        """
        Resolve joint names -> absolute qpos addresses once at init.
        Returns a flat dict: '<side>_<role>' -> qpos_index.
        """
        import mujoco
        names = {
            "left_hip_pitch":    "left_hip_pitch_joint",
            "left_hip_roll":     "left_hip_roll_joint",
            "left_knee":         "left_knee_joint",
            "left_ankle_pitch":  "left_ankle_pitch_joint",
            "right_hip_pitch":   "right_hip_pitch_joint",
            "right_hip_roll":    "right_hip_roll_joint",
            "right_knee":        "right_knee_joint",
            "right_ankle_pitch": "right_ankle_pitch_joint",
            "left_shoulder":     "left_shoulder_pitch_joint",
            "right_shoulder":    "right_shoulder_pitch_joint",
            "left_elbow":        "left_elbow_joint",
            "right_elbow":       "right_elbow_joint",
        }
        result = {}
        for key, jname in names.items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jname)
            if jid >= 0:
                result[key] = model.jnt_qposadr[jid]
        return result

    # ── Public API ────────────────────────────────────────────────────────────

    def set_command(self, vx: float, vy: float, yaw_rate: float) -> None:
        self._cmd_vx  = float(np.clip(vx,       -0.5,  0.5))
        self._cmd_vy  = float(np.clip(vy,       -0.3,  0.3))
        self._cmd_yaw = float(np.clip(yaw_rate, -1.0,  1.0))

    def step(self, model, data, dt: float | None = None) -> None:
        """
        Apply one control step.
        In kinematic mode dt must be the actual wall-clock step (s).
        In pd_stub mode dt is unused (called every mujoco timestep).
        """
        if self._backend == self.KINEMATIC:
            if dt is None:
                dt = float(model.opt.timestep)
            self._step_kinematic(model, data, dt)
        elif self._backend == self.PD_STUB:
            self._step_pd(model, data)
        else:
            self._step_rl(model, data)

    # ── Kinematic backend ────────────────────────────────────────────────────

    def _step_kinematic(self, model, data, dt: float) -> None:
        """
        Move the G1 freejoint at commanded velocity without physics integration.
        Applies a sinusoidal CPG gait when moving forward so the legs animate.
        mj_forward (not mj_step) propagates kinematics and sensor data.
        """
        import mujoco

        # Current heading from qpos quaternion (w, x, y, z) -> yaw
        qw = data.qpos[3];  qz = data.qpos[6]
        theta = 2.0 * np.arctan2(qz, qw)

        # Euler-integrate position (robot frame -> world frame)
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        data.qpos[0] += (self._cmd_vx * cos_t - self._cmd_vy * sin_t) * dt
        data.qpos[1] += (self._cmd_vx * sin_t + self._cmd_vy * cos_t) * dt

        # Update heading
        theta_new    = theta + self._cmd_yaw * dt
        data.qpos[2] = self._stand_z
        data.qpos[3] = np.cos(theta_new / 2.0)   # qw
        data.qpos[4] = 0.0                         # qx
        data.qpos[5] = 0.0                         # qy
        data.qpos[6] = np.sin(theta_new / 2.0)    # qz

        # Advance gait phase proportional to forward speed, then animate joints.
        # When stationary hold the standing pose.
        speed = abs(self._cmd_vx)
        if speed > 0.02:
            self._gait_phase += 2.0 * np.pi * speed / self._stride_len * dt
            self._apply_gait(data, speed)
        else:
            data.qpos[7:] = self._stand_qpos_joints

        data.ctrl[:] = self._stand_ctrl

        # Set qvel consistent with commanded motion so IMU/gyro sensors read
        # correct values after mj_forward (which uses qvel for sensor computation
        # but does not integrate it from qpos).
        cos_tn = np.cos(theta_new);  sin_tn = np.sin(theta_new)
        data.qvel[0] = self._cmd_vx * cos_tn - self._cmd_vy * sin_tn  # world vx
        data.qvel[1] = self._cmd_vx * sin_tn + self._cmd_vy * cos_tn  # world vy
        data.qvel[2] = 0.0   # vz
        data.qvel[3] = 0.0   # wx
        data.qvel[4] = 0.0   # wy
        data.qvel[5] = self._cmd_yaw  # wz (read by torso gyro sensor)

        # Advance simulation time and propagate kinematics + sensors
        data.time += dt
        mujoco.mj_forward(model, data)

    def _apply_gait(self, data, speed: float) -> None:
        """
        Sinusoidal CPG: left leg at phase φ, right leg at φ+π (anti-phase).

        Joints animated (verified qpos addresses from model introspection):
          L hip_pitch=7, L knee=10, L ankle_pitch=11
          R hip_pitch=13, R knee=16, R ankle_pitch=17
          L shoulder=22, R shoulder=29, L elbow=25, R elbow=32

        No body sway or pelvis bob — only sagittal leg swing and arm counter-swing.
        """
        A   = min(0.225, speed / 0.35 * 0.225)  # hip amplitude (rad); ~13° at full speed
        phi = self._gait_phase
        s   = self._stand_qpos_joints           # standing reference (all zeros for G1)

        data.qpos[7:] = s.copy()

        for hp, kn, ap, phase_off in (
            ( 7, 10, 11, 0.0),    # left leg
            (13, 16, 17, np.pi),  # right leg — anti-phase
        ):
            p      = phi + phase_off
            sp     = np.sin(p)
            sp_pos = max(0.0, sp)   # positive half only (swing phase gate)

            # Hip pitch: full ±A sinusoidal swing
            data.qpos[hp] = s[hp - 7] + A * sp

            # Knee: sp² gives a smooth bell that peaks at mid-swing and is
            # exactly zero at both ends of the swing half-cycle.
            # Factor 1.8 makes the knee bend ~46° at full speed — clearly visible.
            data.qpos[kn] = s[kn - 7] + A * 1.8 * sp_pos * sp_pos

            # Ankle pitch: compensates for hip so the foot stays roughly level.
            # Slight plantar flexion when hip is back (push-off), dorsiflexion
            # when hip is forward (foot clearance).
            data.qpos[ap] = s[ap - 7] - A * 0.35 * sp

        # Arms counter-swing: shoulder opposite to ipsilateral leg, elbow bends
        # at extremes of the arm swing.
        gm = self._gait_map
        for side, phase_off in (("left", 0.0), ("right", np.pi)):
            p  = phi + phase_off
            sp = np.sin(p)
            k  = f"{side}_shoulder"
            if k in gm:
                data.qpos[gm[k]] = s[gm[k] - 7] - A * 0.6 * sp
            k = f"{side}_elbow"
            if k in gm:
                data.qpos[gm[k]] = s[gm[k] - 7] + A * 0.3 * abs(sp)

    # ── PD stub ──────────────────────────────────────────────────────────────

    def _step_pd(self, model, data) -> None:
        """Holds joints near standing pose. Robot stays upright but cannot walk."""
        kp, kd = 50.0, 2.0
        joint_qpos = data.qpos[7 : 7 + model.nu]
        joint_qvel = data.qvel[6 : 6 + model.nu]
        data.ctrl[:] = kp * (self._stand_qpos_joints - joint_qpos) - kd * joint_qvel

    # ── RL policy slot ────────────────────────────────────────────────────────

    def _load_rl_policy(self, model) -> None:
        raise NotImplementedError(
            "RL policy integration not implemented. "
            "Provide unitree_rl_gym checkpoint and implement this method."
        )

    def _step_rl(self, model, data) -> None:
        raise NotImplementedError("RL policy integration not implemented.")
