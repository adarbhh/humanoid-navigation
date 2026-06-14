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
| `make maze SEED=N` | Generate maze N, write XML + solution path to `mazes/` |
| `make run SEED=N` | Run one navigation episode (headless) |
| `make record SEED=N` | Run episode + save HDF5 dataset to `runs/` |
| `make batch` | Run 25 held-out seeds headlessly, collect KPIs |
| `make report` | Generate `report/kpi_report.html` from batch results |
| `make demo SEED=N` | Live demo: MuJoCo viewer + real-time browser dashboard |
| `make test` | Run all tests |

---

## Project Structure

```
.
├── setup.sh / setup.bat        # One-command environment setup
├── environment.yml             # Pinned conda/pip dependencies
├── Makefile                    # All entry points
├── runner.py                   # Single episode orchestrator (run / record / demo)
│
├── maze/
│   └── generator.py            # Seeded procedural maze → MuJoCo XML
│
├── robot/
│   ├── model/g1/               # Unitree G1 XML + mesh assets (downloaded)
│   ├── sensors.py              # Sensor extraction from mujoco.Data
│   ├── recorder.py             # Crash-safe HDF5 multi-stream recorder
│   └── walking_policy/         # Velocity command interface
│
├── navigation/
│   ├── occupancy_grid.py       # 2D grid updated from LiDAR scans
│   ├── localization.py         # IMU dead-reckoning + ICP scan matching
│   ├── planner.py              # A* global path planner
│   └── controller.py           # Pure-pursuit local planner → (vx, vy, yaw)
│
├── dashboard/
│   └── index.html              # Live browser KPI dashboard (SSE)
│
├── report/
│   ├── generate_report.py      # KPI report generator → kpi_report.html
│   └── kpi_report.html         # Generated report (after make report)
│
├── scripts/
│   ├── batch_eval.py           # Headless batch runner (25 held-out seeds)
│   └── download_models.py      # Fetch G1 model from MuJoCo Menagerie
│
├── seeds/
│   ├── held_out.txt            # 25 held-out evaluation seeds
│   └── seen.txt                # 10 seen seeds (development)
│
└── tests/
    ├── test_phase1_setup.py    # Environment + model smoke test
    └── test_phase2_maze.py     # Maze generator tests
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
