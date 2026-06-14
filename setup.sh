#!/usr/bin/env bash
# One-command setup for the robotics assignment environment.
# Usage: bash setup.sh
# Tested on: Ubuntu 22.04, macOS 14. For Windows use setup.bat.

set -euo pipefail

ENV_NAME="robotics-assignment"

# ── Pre-flight: require conda ─────────────────────────────────────────────────
if ! command -v conda &>/dev/null; then
    echo ""
    echo "ERROR: conda not found on PATH."
    echo ""
    echo "Please install Miniconda or Anaconda first:"
    echo "  https://docs.conda.io/en/latest/miniconda.html"
    echo ""
    echo "After installing, open a new terminal (so conda is on PATH) and re-run:"
    echo "  bash setup.sh"
    echo ""
    exit 1
fi

echo "conda found: $(conda --version)"
echo ""

# ── Create / update conda environment ─────────────────────────────────────────
echo "==> Creating conda environment '$ENV_NAME' from environment.yml ..."
conda env create -f environment.yml --name "$ENV_NAME" 2>/dev/null \
  || conda env update -f environment.yml --name "$ENV_NAME" --prune

# ── Download robot models ──────────────────────────────────────────────────────
echo ""
echo "==> Downloading robot models (Unitree G1 from MuJoCo Menagerie) ..."
conda run -n "$ENV_NAME" python scripts/download_models.py

# ── Smoke test ─────────────────────────────────────────────────────────────────
echo ""
echo "==> Running Phase 1 smoke tests ..."
conda run -n "$ENV_NAME" python -m pytest tests/test_phase1_setup.py -v --tb=short

echo ""
echo "============================================================"
echo "Setup complete."
echo "Activate with:  conda activate $ENV_NAME"
echo "Run the demo:   make demo SEED=42"
echo "Run all tests:  make test"
echo "============================================================"
