@echo off
setlocal

set SEED=%1
if "%SEED%"=="" set SEED=42

set PLANNER=%2
if "%PLANNER%"=="" set PLANNER=astar

set SPEED=%3
if "%SPEED%"=="" set SPEED=2.0

echo.
echo  *** PLANNER DEMO ***
echo  Seed=%SEED%   Planner=%PLANNER%   Speed=%SPEED%x
echo.
echo  Planners: astar  dijkstra  wastar3  wastar10
echo.

conda run -n robotics-assignment python runner_planner.py --seed %SEED% --planner %PLANNER% --speed %SPEED% --demo

endlocal
