"""Print full G1 body/joint/actuator/sensor inventory."""
import mujoco, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
model = mujoco.MjModel.from_xml_path(str(ROOT / "robot/model/g1/scene.xml"))

print("=== BODIES ===")
for i in range(model.nbody):
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i)
    print(f"  [{i:2d}] {name}")

print("\n=== JOINTS ===")
for i in range(model.njnt):
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
    jtype = ["free", "ball", "slide", "hinge"][model.jnt_type[i]]
    print(f"  [{i:2d}] {name}  ({jtype})")

print("\n=== ACTUATORS ===")
for i in range(model.nu):
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
    print(f"  [{i:2d}] {name}")

print("\n=== SENSORS ===")
for i in range(model.nsensor):
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_SENSOR, i)
    print(f"  [{i:2d}] {name}")

print(f"\ntimestep: {model.opt.timestep}s  ({1/model.opt.timestep:.0f} Hz)")
print(f"nq={model.nq}  nv={model.nv}  nu={model.nu}  nbody={model.nbody}  njnt={model.njnt}")
