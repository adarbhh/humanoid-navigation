#!/usr/bin/env bash
# One-command setup for the robotics assignment environment.
# Usage: bash setup.sh
# Tested on: Ubuntu 22.04, macOS 14. For Windows use setup.bat.

set -euo pipefail

ENV_NAME="robotics-assignment"

echo "==> Creating conda environment '$ENV_NAME' from environment.yml ..."
conda env create -f environment.yml --name "$ENV_NAME" 2>/dev/null \
  || conda env update -f environment.yml --name "$ENV_NAME" --prune

echo "==> Downloading robot models (Unitree G1 from MuJoCo Menagerie) ..."
conda run -n "$ENV_NAME" python scripts/download_models.py

echo "==> Running Phase 1 smoke test (MuJoCo + G1 model load) ..."
conda run -n "$ENV_NAME" python tests/test_phase1_setup.py

echo ""
echo "Setup complete. Activate with:"
echo "  conda activate $ENV_NAME"
echo "Then run the demo with:"
echo "  make demo SEED=42"
