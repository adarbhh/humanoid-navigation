"""
runner_fault.py — Fault-injection demo: right leg mechanical failure.

Visible faults:
  1. Right leg COMPLETELY FROZEN in a mid-stride pose (no animation)
  2. Robot body visibly LEANS RIGHT (~15 deg roll) — like a real limp
  3. Robot moves at 50% of normal speed
  4. Subtle rightward drift accumulates localization error

Usage:
    conda run -n robotics-assignment python runner_fault.py --seed 42 --demo
"""

import sys
import math
import argparse
from pathlib import Path
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Fault parameters ──────────────────────────────────────────────────────────
_BODY_LEAN_DEG  = 15.0   # rightward roll lean (degrees) — visible but not crippling
_SPEED_PENALTY  = 0.15   # robot moves at 85% speed — noticeable but not extreme
_LATERAL_DRIFT  = 0.021  # 1.6% of fwd speed rightward drift — causes more collisions but not trapping

# Right leg frozen joint angles (mid-stride pose — looks like it got stuck)
_RIGHT_HIP_FROZEN   =  0.18   # rad — hip slightly forward
_RIGHT_KNEE_FROZEN  =  0.55   # rad — knee bent (most visible from above)
_RIGHT_ANKLE_FROZEN = -0.06   # rad — ankle slightly down

# ── Patch gait: right leg frozen, left leg normal ─────────────────────────────
from robot.walking_policy.interface import WalkingPolicyInterface

_original_apply_gait = WalkingPolicyInterface._apply_gait


def _faulty_apply_gait(self, data, speed: float) -> None:
    A   = min(0.225, speed / 0.35 * 0.225)
    phi = self._gait_phase
    s   = self._stand_qpos_joints

    data.qpos[7:] = s.copy()

    # ── Left leg: animate normally ────────────────────────────────────────────
    hp, kn, ap = 7, 10, 11
    p      = phi
    sp     = np.sin(p)
    sp_pos = max(0.0, sp)
    data.qpos[hp] = s[hp - 7] + A * sp
    data.qpos[kn] = s[kn - 7] + A * 1.8 * sp_pos * sp_pos
    data.qpos[ap] = s[ap - 7] - A * 0.35 * sp

    # ── Right leg: COMPLETELY FROZEN in a mid-stride pose ────────────────────
    data.qpos[13] = _RIGHT_HIP_FROZEN
    data.qpos[16] = _RIGHT_KNEE_FROZEN
    data.qpos[17] = _RIGHT_ANKLE_FROZEN

    # Arms: only left arm swings (right arm also stiff to match right side fault)
    gm = self._gait_map
    k = "left_shoulder"
    if k in gm:
        data.qpos[gm[k]] = s[gm[k] - 7] - A * 0.6 * np.sin(phi)
    k = "left_elbow"
    if k in gm:
        data.qpos[gm[k]] = s[gm[k] - 7] + A * 0.3 * abs(np.sin(phi))
    # Right arm barely moves
    k = "right_shoulder"
    if k in gm:
        data.qpos[gm[k]] = s[gm[k] - 7] + 0.08
    k = "right_elbow"
    if k in gm:
        data.qpos[gm[k]] = s[gm[k] - 7] + 0.12


WalkingPolicyInterface._apply_gait = _faulty_apply_gait


# ── Patch kinematic step: body lean + speed penalty + drift ──────────────────
_original_step_kinematic = WalkingPolicyInterface._step_kinematic
_LEAN_RAD = math.radians(_BODY_LEAN_DEG)


def _faulty_step_kinematic(self, model, data, dt: float) -> None:
    import mujoco

    # 50% speed before the normal movement step
    saved_vx = self._cmd_vx
    self._cmd_vx *= (1.0 - _SPEED_PENALTY)
    _original_step_kinematic(self, model, data, dt)
    self._cmd_vx = saved_vx

    # Current heading yaw
    qw = data.qpos[3]; qz = data.qpos[6]
    theta = 2.0 * math.atan2(qz, qw)

    # Rightward body lean (roll about the forward axis)
    # Compose yaw * roll quaternions:
    #   yaw_q  = [cos(θ/2),   0,          0,         sin(θ/2)]
    #   roll_q = [cos(r/2),   sin(r/2),   0,         0       ]
    # product  = yaw_q ⊗ roll_q
    hy = theta / 2.0
    hr = _LEAN_RAD / 2.0
    cw, sw = math.cos(hy), math.sin(hy)
    cr, sr = math.cos(hr), math.sin(hr)
    data.qpos[3] = cw * cr          # qw
    data.qpos[4] = cw * sr          # qx  (rightward roll)
    data.qpos[5] = sw * sr          # qy
    data.qpos[6] = sw * cr          # qz

    # Rightward lateral drift
    cos_t = math.cos(theta); sin_t = math.sin(theta)
    drift = self._cmd_vx * _LATERAL_DRIFT * dt
    data.qpos[0] +=  drift * sin_t
    data.qpos[1] -=  drift * cos_t

    mujoco.mj_forward(model, data)


WalkingPolicyInterface._step_kinematic = _faulty_step_kinematic


# ── Stuck event notifier: pauses viewer so you can SEE it ─────────────────────
import time
from collections import deque as _deque

_pos_window:   _deque = _deque(maxlen=20)   # 20 ticks = 1 s at 20 Hz
_stuck_count:  int   = 0
_in_stuck_vis: bool  = False
_PAUSE_S               = 2.0   # real-time pause so viewer shows the stuck pose

_faulty_step_ref = WalkingPolicyInterface._step_kinematic


def _detecting_step_kinematic(self, model, data, dt: float) -> None:
    global _stuck_count, _in_stuck_vis

    _faulty_step_ref(self, model, data, dt)

    px, py = float(data.qpos[0]), float(data.qpos[1])
    _pos_window.append((px, py))

    if len(_pos_window) == 20:
        x0, y0 = _pos_window[0]
        disp = math.hypot(px - x0, py - y0)

        if not _in_stuck_vis and disp < 0.05:
            _stuck_count += 1
            _in_stuck_vis = True
            print("\n" + "!" * 70)
            print(f"  *** STUCK EVENT #{_stuck_count} at t={data.time:.1f}s  pos=({px:.2f},{py:.2f}) ***")
            print(f"      Displacement last 1s: {disp*100:.1f} cm  -- pausing {_PAUSE_S:.0f}s to observe")
            print("!" * 70)
            _pos_window.clear()
            time.sleep(_PAUSE_S)   # freeze real time; viewer keeps rendering the stuck pose

        elif _in_stuck_vis and disp > 0.10:
            _in_stuck_vis = False
            print(f"  *** RECOVERED from event #{_stuck_count} at t={data.time:.1f}s ***\n")


WalkingPolicyInterface._step_kinematic = _detecting_step_kinematic

# ── Import and run ────────────────────────────────────────────────────────────
from runner import run_episode, DIFFICULTY_PRESETS

print("\n" + "=" * 70)
print("  FAULT INJECTION — RIGHT LEG MECHANICAL FAILURE")
print(f"    Right leg          : FROZEN in mid-stride (hip {_RIGHT_HIP_FROZEN:.2f} rad,"
      f" knee {_RIGHT_KNEE_FROZEN:.2f} rad)")
print(f"    Body lean          : {_BODY_LEAN_DEG:.0f} deg rightward roll")
print(f"    Speed              : {(1-_SPEED_PENALTY)*100:.0f}% of normal  (30% slower)")
print(f"    Lateral drift      : {_LATERAL_DRIFT*100:.0f}% per m/s forward (arcs right on straights)")
print(f"    Stuck behavior     : back-up + left-right oscillation (~2s visible struggle)")
print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="G1 maze runner with right-leg fault injection"
    )
    parser.add_argument("--seed",       type=int,   default=42)
    parser.add_argument("--grid-size",  type=int,   default=10)
    parser.add_argument("--max-time",   type=float, default=300.0)
    parser.add_argument("--no-viz",     action="store_true")
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
        speed=args.speed,
        demo=args.demo,
    )


if __name__ == "__main__":
    main()
