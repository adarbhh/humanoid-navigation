@echo off
echo START

SET ENV_NAME=robotics-assignment

REM ── Locate conda ─────────────────────────────────────────────────────────
REM Search well-known install locations. CONDA_EXE will hold the full path
REM to conda.bat so we never rely on PATH being set correctly.

SET CONDA_EXE=

REM 1. Already on PATH?
FOR /F "tokens=*" %%P IN ('where conda 2^>NUL') DO (
    IF "%%~xP"==".bat" SET CONDA_EXE=%%P
    IF "%%~xP"==".exe" SET CONDA_EXE=%%P
)

REM 2. Common install locations
IF "%CONDA_EXE%"=="" IF EXIST "C:\ProgramData\anaconda3.9\Scripts\conda.exe"      SET CONDA_EXE=C:\ProgramData\anaconda3.9\Scripts\conda.exe
IF "%CONDA_EXE%"=="" IF EXIST "C:\ProgramData\anaconda3.9\Library\bin\conda.bat"   SET CONDA_EXE=C:\ProgramData\anaconda3.9\Library\bin\conda.bat
IF "%CONDA_EXE%"=="" IF EXIST "C:\ProgramData\anaconda3\Scripts\conda.exe"         SET CONDA_EXE=C:\ProgramData\anaconda3\Scripts\conda.exe
IF "%CONDA_EXE%"=="" IF EXIST "C:\ProgramData\miniconda3\Scripts\conda.exe"        SET CONDA_EXE=C:\ProgramData\miniconda3\Scripts\conda.exe
IF "%CONDA_EXE%"=="" IF EXIST "%USERPROFILE%\anaconda3\Scripts\conda.exe"          SET CONDA_EXE=%USERPROFILE%\anaconda3\Scripts\conda.exe
IF "%CONDA_EXE%"=="" IF EXIST "%USERPROFILE%\miniconda3\Scripts\conda.exe"         SET CONDA_EXE=%USERPROFILE%\miniconda3\Scripts\conda.exe
IF "%CONDA_EXE%"=="" IF EXIST "%USERPROFILE%\anaconda3.9\Scripts\conda.exe"        SET CONDA_EXE=%USERPROFILE%\anaconda3.9\Scripts\conda.exe

IF "%CONDA_EXE%"=="" (
    echo.
    echo ERROR: conda not found.
    echo Please install Miniconda or Anaconda, then re-run this script.
    echo   https://docs.conda.io/en/latest/miniconda.html
    echo.
    pause
    exit /b 1
)

echo conda found: %CONDA_EXE%
CALL "%CONDA_EXE%" --version
echo.

REM ── Create / update conda environment ────────────────────────────────────
echo =^> Creating conda environment '%ENV_NAME%' from environment.yml ...
CALL "%CONDA_EXE%" env create -f environment.yml --name %ENV_NAME%
IF ERRORLEVEL 1 (
    echo    [env exists - updating...]
    CALL "%CONDA_EXE%" env update -f environment.yml --name %ENV_NAME% --prune
    IF ERRORLEVEL 1 (
        echo ERROR: Failed to create or update conda environment.
        pause
        exit /b 1
    )
)

REM ── Download robot models ─────────────────────────────────────────────────
echo.
echo =^> Downloading robot models (Unitree G1 from MuJoCo Menagerie) ...
CALL "%CONDA_EXE%" run -n %ENV_NAME% python scripts/download_models.py
IF ERRORLEVEL 1 (
    echo ERROR: Model download failed. Check your internet connection and retry.
    pause
    exit /b 1
)

REM ── Smoke tests ───────────────────────────────────────────────────────────
echo.
echo =^> Running Phase 1 smoke tests ...
CALL "%CONDA_EXE%" run -n %ENV_NAME% python -m pytest tests/test_phase1_setup.py -v --tb=short
IF ERRORLEVEL 1 (
    echo ERROR: Smoke tests failed. See output above for details.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Setup complete.
echo  Activate with:  conda activate %ENV_NAME%
echo  Run the demo:   make demo SEED=42
echo  Run all tests:  make test
echo ============================================================
pause
