import mujoco, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from maze.generator import MazeGrid, MazeScene

grid  = MazeGrid(seed=42)
scene = MazeScene(grid, Path(__file__).parent.parent / "robot/model/g1/scene.xml")
_, spec = scene.build()
model = spec.compile()

print(f"njnt = {model.njnt}")
for i in range(model.njnt):
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
    adr  = model.jnt_qposadr[i]
    print(f"  [{i:2d}] qpos[{adr:2d}]  {name}")
