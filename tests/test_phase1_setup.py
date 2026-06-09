"""
Phase 1 smoke test: MuJoCo loads, G1 model loads, basic sim step works.
Run standalone: python tests/test_phase1_setup.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def test_mujoco_import():
    import mujoco
    print(f"  mujoco {mujoco.__version__}  OK")
    return mujoco


def test_numpy_import():
    import numpy as np
    print(f"  numpy {np.__version__}  OK")


def test_g1_model_exists():
    model_dir = ROOT / "robot" / "model" / "g1"
    candidates = list(model_dir.glob("*.xml")) if model_dir.exists() else []
    if not candidates:
        print(f"  ERROR: no XML files in {model_dir}")
        print(f"  Run: python scripts/download_models.py")
        sys.exit(1)
    print(f"  G1 model dir: {model_dir}")
    for f in sorted(candidates):
        print(f"    {f.name}")
    return candidates


def test_g1_loads(mujoco, xml_files):
    """Load the G1 scene XML and confirm expected joints/sensors exist."""
    # Prefer scene.xml (has floor + lighting), fall back to g1.xml
    scene = next((x for x in xml_files if x.name == "scene.xml"), xml_files[0])
    print(f"  Loading {scene.name} ...")

    model = mujoco.MjModel.from_xml_path(str(scene))
    data  = mujoco.MjData(model)

    print(f"  nq={model.nq}  nv={model.nv}  nu={model.nu}  nbody={model.nbody}")
    assert model.nq > 0,  "No DoFs found — model may be wrong"
    assert model.nu > 0,  "No actuators found"
    print(f"  Model loaded  OK")
    return model, data


def test_sim_step(mujoco, model, data):
    """Run 100 steps and confirm sim time advances without NaN."""
    import numpy as np
    mujoco.mj_resetData(model, data)
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert np.isfinite(data.qpos).all(), "qpos contains NaN/Inf after 100 steps"
    assert data.time > 0, "Simulation time did not advance"
    print(f"  100 sim steps  OK  (sim_time={data.time:.4f}s)")


def test_bodies_and_joints(model):
    """Print body/joint names to confirm G1 structure."""
    import mujoco
    print("  Bodies:")
    for i in range(min(model.nbody, 10)):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i)
        print(f"    [{i}] {name}")
    if model.nbody > 10:
        print(f"    ... and {model.nbody - 10} more")


def main():
    print("\n=== Phase 1 Setup Verification ===\n")
    errors = []

    try:
        mujoco = test_mujoco_import()
    except Exception as e:
        print(f"  FAIL mujoco import: {e}")
        sys.exit(1)

    try:
        test_numpy_import()
    except Exception as e:
        errors.append(f"numpy: {e}")

    try:
        xml_files = test_g1_model_exists()
    except SystemExit:
        raise
    except Exception as e:
        errors.append(f"model files: {e}")
        xml_files = []

    if xml_files:
        try:
            model, data = test_g1_loads(mujoco, xml_files)
            test_sim_step(mujoco, model, data)
            test_bodies_and_joints(model)
        except Exception as e:
            errors.append(f"G1 sim: {e}")

    print()
    if errors:
        print("FAILURES:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("=== All Phase 1 checks PASSED ===")


if __name__ == "__main__":
    main()
