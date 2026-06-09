# Robotics Ops Engineer — Home Assignment

Unitree G1 in MuJoCo, procedurally generated mazes, closed-loop navigation, multi-sensor data collection, and KPI analysis.

## Quick Start

### 1. One-command setup

```bash
# Linux / macOS
bash setup.sh

# Windows
setup.bat
```

This creates the `robotics-assignment` conda environment, downloads the Unitree G1
model from MuJoCo Menagerie, and runs the Phase 1 smoke test.

### 2. Activate the environment

```bash
conda activate robotics-assignment
```

### 3. Live demo (the money shot)

```bash
make demo SEED=42        # deterministic maze + navigation + live KPI view
make demo SEED=$RANDOM   # fresh random maze
```

---

## Entry Points

| Command | What it does |
|---------|--------------|
| `make setup` | Full one-command environment setup |
| `make maze SEED=N` | Generate maze N, write XML + solution path |
| `make run SEED=N` | Run one navigation episode, record dataset |
| `make batch` | Run 20 held-out seeds, collect KPIs |
| `make report` | Execute analysis notebook → HTML report |
| `make demo SEED=N` | Live demo with real-time KPI dashboard |
| `make test` | Run all tests |

---

## Project Structure

```
.
├── setup.sh / setup.bat        # One-command environment setup
├── environment.yml             # Pinned conda/pip dependencies
├── Makefile                    # All entry points
├── runner.py                   # Single episode orchestrator
├── batch_runner.py             # Parallel batch runner
├── demo.py                     # Live demo with dashboard
│
├── maze/
│   └── generator.py            # Seeded procedural maze → MuJoCo XML
│
├── robot/
│   ├── model/g1/               # Unitree G1 XML + mesh assets (downloaded)
│   ├── sensors.py              # Sensor extraction from mujoco.Data
│   └── walking_policy/         # Velocity command interface
│
├── navigation/
│   ├── occupancy_grid.py       # 2D grid updated from LiDAR scans
│   ├── localization.py         # IMU dead-reckoning + ICP scan matching
│   ├── planner.py              # A* global path planner
│   └── controller.py          # Pure-pursuit local planner → (vx, vy, yaw)
│
├── data/
│   ├── recorder.py             # Crash-safe HDF5 multi-stream recorder
│   └── schema.py               # Stream definitions and dtypes
│
├── analysis/
│   ├── kpi.py                  # KPI computation from HDF5 datasets
│   └── report.ipynb            # KPI report notebook
│
├── scripts/
│   └── download_models.py      # Fetch G1 model from MuJoCo Menagerie
│
└── tests/
    └── test_phase1_setup.py    # Phase 1 smoke test
```

---

## Hard Rule

> The navigation stack does **not** consume MuJoCo ground-truth pose.
> GT pose is recorded in `gt_pose` stream for scoring only.

---

## KPIs

See §3 of the assignment for the full KPI list. Summary:

- **Solve rate** ≥ 20 held-out seeds, 95% CI
- **Path efficiency**: traveled / optimal
- **Wall collisions**, **stuck events + recovery time**
- **ATE vs GT**: localization RMSE
- **Data quality**: fps, drop rate, sync error, schema completeness
- **Crash safety**: dataset valid after SIGKILL

---

## Dependencies

- [MuJoCo 3.3.7](https://mujoco.org/)
- [MuJoCo Menagerie — Unitree G1](https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1)
- Python 3.10, NumPy, SciPy, h5py, matplotlib, rich
