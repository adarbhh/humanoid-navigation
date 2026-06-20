@echo off
setlocal

set SEED=%1
if "%SEED%"=="" set SEED=42

set SPEED=%2
if "%SPEED%"=="" set SPEED=10.0

echo Launching side-by-side comparison: seed=%SEED%  speed=%SPEED%x
echo   Left window  : normal robot (runner.py)
echo   Right window : dynamic obstacle (runner_dynamic.py)
echo.

start "Normal Robot  [seed=%SEED%]" conda run -n robotics-assignment python runner.py --seed %SEED% --speed %SPEED% --demo
timeout /t 2 /nobreak >nul
start "Dynamic Obstacle  [seed=%SEED%]" conda run -n robotics-assignment python runner_dynamic.py --seed %SEED% --speed %SPEED% --demo

endlocal
