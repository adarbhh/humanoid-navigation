@echo off
setlocal

set SEED=%1
if "%SEED%"=="" set SEED=42

set SPEED=%2
if "%SPEED%"=="" set SPEED=2.0

echo.
echo  *** DIJKSTRA PLANNER DEMO ***
echo  Seed=%SEED%   Speed=%SPEED%x
echo.

conda run -n robotics-assignment python runner.py --seed %SEED% --speed %SPEED% --planner dijkstra --demo

endlocal
