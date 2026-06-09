@echo off
REM One-command setup for Windows.
REM Usage: setup.bat

SET ENV_NAME=robotics-assignment

echo =^> Creating conda environment '%ENV_NAME%' from environment.yml ...
conda env create -f environment.yml --name %ENV_NAME% 2>NUL || conda env update -f environment.yml --name %ENV_NAME% --prune

echo =^> Downloading robot models ...
conda run -n %ENV_NAME% python scripts/download_models.py

echo =^> Running Phase 1 smoke test ...
conda run -n %ENV_NAME% python tests/test_phase1_setup.py

echo.
echo Setup complete. Activate with:
echo   conda activate %ENV_NAME%
