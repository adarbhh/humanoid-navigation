"""Confirm gait map is populated and that joint values actually change."""
import sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import mujoco
from maze.generator import MazeGrid, MazeScene
from robot.walking_policy.interface import WalkingPolicyInterface

grid  = MazeGrid(seed=42)
scene = MazeScene(grid, Path(__file__).parent.parent / "robot/model/g1/scene.xml")
_, spec = scene.build()
model = spec.compile()
data  = mujoco.MjData(model)
mujoco.mj_resetDataKeyframe(model, data, 0)
mujoco.mj_forward(model, data)

policy = WalkingPolicyInterface(model, backend="kinematic")
print("gait_map:", policy._gait_map)
print("stand qpos[7:13]:", policy._stand_qpos_joints[:6])

# Simulate 10 ticks at full speed forward
policy.set_command(0.35, 0.0, 0.0)
for tick in range(10):
    policy.step(model, data, dt=0.05)
    hp_l = data.qpos[7]
    hp_r = data.qpos[13]
    kn_l = data.qpos[10]
    kn_r = data.qpos[16]
    print(f"tick {tick:2d}  phase={policy._gait_phase:.2f}  "
          f"L_hip={hp_l:.3f}  R_hip={hp_r:.3f}  "
          f"L_knee={kn_l:.3f}  R_knee={kn_r:.3f}")
