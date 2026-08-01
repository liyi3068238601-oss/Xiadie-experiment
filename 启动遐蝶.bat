@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "SCRIPT=%ROOT%scripts\start-dev.ps1"
set "BACKEND=%ROOT%backend\.venv\Scripts\python.exe"
set "ELECTRON=%ROOT%desktop\node_modules\electron\dist\electron.exe"
set "LOGROOT=%LOCALAPPDATA%\Xiadie-Experiment\dev-logs"

if not defined LOCALAPPDATA set "LOGROOT=%TEMP%\Xiadie-Experiment\dev-logs"
if not exist "%LOGROOT%" mkdir "%LOGROOT%" >nul 2>&1
>"%LOGROOT%\bat-launch.log" echo [%date% %time%] Starting Xiadie Experiment from "%ROOT%"

if not exist "%POWERSHELL%" goto :missing_powershell
if not exist "%SCRIPT%" goto :missing_script
if not exist "%BACKEND%" goto :missing_backend
if not exist "%ELECTRON%" goto :missing_electron

rem Run the launcher in this console. The console stays available for diagnostics
rem and closes normally after the experiment application exits.
"%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 goto :start_failed
exit /b 0

:missing_powershell
set "ERROR_MESSAGE=Windows PowerShell was not found: %POWERSHELL%"
goto :failed

:missing_script
set "ERROR_MESSAGE=Launcher script was not found: %SCRIPT%"
goto :failed

:missing_backend
set "ERROR_MESSAGE=Backend environment is incomplete: %BACKEND%"
goto :failed

:missing_electron
set "ERROR_MESSAGE=Electron runtime is incomplete: %ELECTRON%"
goto :failed

:start_failed
set "ERROR_MESSAGE=Windows could not start the experiment launcher."

:failed
>>"%LOGROOT%\bat-launch.log" echo [%date% %time%] ERROR: %ERROR_MESSAGE%
echo.
echo %ERROR_MESSAGE%
echo See log: "%LOGROOT%\bat-launch.log"
echo.
pause
exit /b 1
