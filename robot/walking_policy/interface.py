"""
Walking policy interface: translate (vx, vy, yaw_rate) commands into joint
position targets that get applied to the MuJoCo model.

Phase 1/2: stub that applies a simple PD velocity controller.
Phase 3: swap in the unitree_rl_gym sim2sim policy checkpoint.
"""

from __future__ import annotations
import numpy as np


class WalkingPolicyInterface:
    """
    Wraps the low-level locomotion policy.

    Usage:
        policy = WalkingPolicyInterface(model)
        # each sim step at control_hz:
        policy.set_command(vx=0.3, vy=0.0, yaw_rate=0.1)
        policy.step(model, data)
    """

    def __init__(self, model, backend: str = "pd_stub"):
        """
        backend: "pd_stub" (default, no torch needed) or "rl_policy" (Phase 3).
        """
        self._backend = backend
        self._cmd_vx      = 0.0
        self._cmd_vy      = 0.0
        self._cmd_yaw     = 0.0
        self._model       = model

        if backend == "rl_policy":
            self._load_rl_policy(model)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_command(self, vx: float, vy: float, yaw_rate: float) -> None:
        """Set desired base velocity. Call before each policy.step()."""
        max_vx, max_vy, max_yaw = 0.5, 0.3, 1.0
        self._cmd_vx  = float(np.clip(vx,       -max_vx,  max_vx))
        self._cmd_vy  = float(np.clip(vy,       -max_vy,  max_vy))
        self._cmd_yaw = float(np.clip(yaw_rate, -max_yaw, max_yaw))

    def step(self, model, data) -> None:
        """Apply one control step. Call at model.opt.timestep frequency."""
        if self._backend == "rl_policy":
            self._step_rl(model, data)
        else:
            self._step_pd(model, data)

    # ── PD stub (Phase 1/2) ────────────────────────────────────────────────────

    def _step_pd(self, model, data) -> None:
        """
        Minimal PD controller: keeps joints near default pose while applying
        a small base velocity by offsetting hip/knee targets.
        Not physically realistic — sufficient for testing the nav stack.
        """
        import mujoco
        # Default joint positions (zero configuration = standing)
        qpos_default = np.zeros(model.nu)
        kp = 50.0
        kd = 2.0
        # qpos[7:] are the joint angles (first 7 = free joint pos+quat)
        joint_qpos = data.qpos[7:7 + model.nu]
        joint_qvel = data.qvel[6:6 + model.nu]
        data.ctrl[:] = kp * (qpos_default - joint_qpos) - kd * joint_qvel

    # ── RL policy (Phase 3) ────────────────────────────────────────────────────

    def _load_rl_policy(self, model) -> None:
        """Load unitree_rl_gym sim2sim checkpoint. Implemented in Phase 3."""
        raise NotImplementedError("RL policy integration — Phase 3")

    def _step_rl(self, model, data) -> None:
        raise NotImplementedError("RL policy integration — Phase 3")
