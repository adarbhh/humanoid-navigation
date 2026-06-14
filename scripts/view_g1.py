"""Launch the MuJoCo interactive viewer with the G1 standing in its default pose."""
import time
import mujoco
import mujoco.viewer
from pathlib import Path

ROOT = Path(__file__).parent.parent
scene = ROOT / "robot" / "model" / "g1" / "scene.xml"

model = mujoco.MjModel.from_xml_path(str(scene))
data  = mujoco.MjData(model)
mujoco.mj_resetData(model, data)

print(f"Loaded G1: nq={model.nq}  nu={model.nu}  nbody={model.nbody}")
print("Opening viewer — close the window to exit.")

with mujoco.viewer.launch_passive(model, data) as viewer:
    # Slow the sim down so the robot falls in real-time (no controller yet)
    while viewer.is_running():
        mujoco.mj_step(model, data)
        viewer.sync()
        time.sleep(model.opt.timestep)  # real-time at 500 Hz
