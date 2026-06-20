@echo off
setlocal

set SEED=%1
if "%SEED%"=="" set SEED=35086

set SPEED=%2
if "%SPEED%"=="" set SPEED=2.0

echo.
echo  *** FAULT INJECTION DEMO ***
echo  Right leg: 50%% hip ROM  /  60%% knee bending  /  ankle compensation OFF
echo  Seed=%SEED%   Speed=%SPEED%x
echo.

conda run -n robotics-assignment python runner_fault.py --seed %SEED% --speed %SPEED% --demo

endlocal
