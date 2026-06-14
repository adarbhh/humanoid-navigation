"""Check available MjSpec body/sensor API in mujoco 3.3.7."""
import mujoco, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = mujoco.MjSpec.from_file(str(ROOT / "robot/model/g1/scene.xml"))

print("=== MjSpec top-level methods ===")
print([m for m in dir(spec) if not m.startswith("_")])

print("\n=== MjsBody methods ===")
print([m for m in dir(spec.worldbody) if not m.startswith("_")])

# Try finding torso_link - check if find_body exists
print("\n=== find_body test ===")
if hasattr(spec, "find_body"):
    b = spec.find_body("torso_link")
    print(f"spec.find_body('torso_link') -> {b}")
else:
    print("spec.find_body not available")

# Try iterating worldbody children
print("\n=== worldbody.bodies type ===")
if hasattr(spec.worldbody, "bodies"):
    print(f"type: {type(spec.worldbody.bodies)}")
    try:
        print(f"len: {len(spec.worldbody.bodies)}")
    except:
        pass
    for b in spec.worldbody.bodies:
        print(f"  child: {b.name}")
        break
else:
    print("no .bodies attribute")

print("\n=== add_sensor test ===")
if hasattr(spec, "add_sensor"):
    print("spec.add_sensor() available")
    s = spec.add_sensor()
    print(f"sensor type: {type(s)}")
    print(f"sensor attrs: {[m for m in dir(s) if not m.startswith('_')]}")
else:
    print("spec.add_sensor() NOT available")
    print("alternatives:", [m for m in dir(spec) if "sensor" in m.lower()])

print("\n=== add_camera on body ===")
wb = spec.worldbody
if hasattr(wb, "add_camera"):
    print("body.add_camera() available")
    cam = wb.add_camera()
    print(f"camera attrs: {[m for m in dir(cam) if not m.startswith('_')]}")
else:
    print("body.add_camera() NOT available")
    print("alternatives:", [m for m in dir(wb) if "cam" in m.lower()])
