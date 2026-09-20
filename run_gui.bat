@echo off
setlocal

cd /d "%~dp0"

if exist "_vendor" (
    set "PYTHONPATH=%CD%\_vendor;%PYTHONPATH%"
)

set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 set "PYEXE=py"

if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE (
    echo [ERROR] Python not found.
    echo Please install Python 3.11+ and check "Add Python to PATH".
    echo Download: https://www.python.org/downloads/
    goto :end
)

echo Using interpreter: %PYEXE%
echo Starting...
echo.

%PYEXE% "gui\app.py"
set "EXITCODE=%errorlevel%"

echo.
if "%EXITCODE%"=="0" (
    echo Program exited normally.
) else (
    echo [ERROR] Program exited with code: %EXITCODE%
    echo.
    echo Please screenshot the error above.
)

:end
echo.
pause
endlocal
