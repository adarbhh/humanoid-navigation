"""
Phase 1 smoke test: MuJoCo loads, G1 model loads, basic sim step works.

Run with pytest:   pytest tests/test_phase1_setup.py -v
Run standalone:    python tests/test_phase1_setup.py
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
MODEL_DIR = ROOT / "robot" / "model" / "g1"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mj():
    import mujoco
    return mujoco


@pytest.fixture(scope="module")
def scene_xml():
    candidates = list(MODEL_DIR.glob("*.xml")) if MODEL_DIR.exists() else []
    assert candidates, (
        f"No XML files in {MODEL_DIR}. Run: python scripts/download_models.py"
    )
    scene = next((x for x in candidates if x.name == "scene.xml"), candidates[0])
    return scene


@pytest.fixture(scope="module")
def model_data(mj, scene_xml):
    model = mj.MjModel.from_xml_path(str(scene_xml))
    data  = mj.MjData(model)
    return model, data


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_mujoco_version(mj):
    """MuJoCo import and version check."""
    parts = [int(x) for x in mj.__version__.split(".")]
    assert parts[0] >= 3, f"Expected mujoco >= 3.x, got {mj.__version__}"


def test_g1_xml_files_exist():
    """G1 model directory contains expected XML files."""
    assert MODEL_DIR.exists(), f"Model dir missing: {MODEL_DIR}"
    xmls = {x.name for x in MODEL_DIR.glob("*.xml")}
    for expected in ("g1.xml", "scene.xml"):
        assert expected in xmls, f"{expected} missing from model dir"


def test_g1_model_loads(model_data):
    """G1 scene.xml loads without error and has sane dimensions."""
    model, _ = model_data
    assert model.nq == 36,  f"Expected nq=36, got {model.nq}"
    assert model.nv == 35,  f"Expected nv=35, got {model.nv}"
    assert model.nu == 29,  f"Expected nu=29, got {model.nu}"
    assert model.nbody == 31, f"Expected nbody=31, got {model.nbody}"


def test_sim_runs_100_steps(mj, model_data):
    """100 simulation steps complete with no NaN/Inf in state."""
    model, data = model_data
    mj.mj_resetData(model, data)
    for _ in range(100):
        mj.mj_step(model, data)
    assert np.isfinite(data.qpos).all(), "qpos contains NaN/Inf after 100 steps"
    assert np.isfinite(data.qvel).all(), "qvel contains NaN/Inf after 100 steps"
    assert data.time > 0, "Simulation time did not advance"


def test_imu_sensors_present(mj, model_data):
    """Named IMU sensors from Menagerie G1 model exist."""
    model, _ = model_data
    expected = {
        "imu-torso-angular-velocity",
        "imu-torso-linear-acceleration",
        "imu-pelvis-angular-velocity",
        "imu-pelvis-linear-acceleration",
    }
    found = set()
    for i in range(model.nsensor):
        name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_SENSOR, i)
        if name in expected:
            found.add(name)
    assert found == expected, f"Missing sensors: {expected - found}"


def test_pelvis_body_exists(mj, model_data):
    """Pelvis body (used for GT pose extraction) resolves correctly."""
    model, _ = model_data
    bid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, "pelvis")
    assert bid >= 0, "Body 'pelvis' not found in model"


def test_model_timestep(model_data):
    """Simulation timestep is 2ms (500 Hz) as expected for G1."""
    model, _ = model_data
    assert abs(model.opt.timestep - 0.002) < 1e-6, (
        f"Expected timestep=0.002, got {model.opt.timestep}"
    )


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
