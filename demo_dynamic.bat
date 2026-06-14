@echo off
setlocal

set SEED=%1
if "%SEED%"=="" set SEED=42

set SPEED=%2
if "%SPEED%"=="" set SPEED=2.0

echo Running dynamic demo: seed=%SEED%  speed=%SPEED%x  (sliding gate enabled)
conda run -n robotics-assignment python runner_dynamic.py --seed %SEED% --speed %SPEED% --demo

endlocal
