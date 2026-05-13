@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo  NetStock — Windows EXE Builder
echo ============================================================
echo.

:: ── Check Python is on PATH ──────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo         Install Python 3.10+ and make sure it is in your PATH.
    pause
    exit /b 1
)

:: ── Install / upgrade PyInstaller ────────────────────────────────────────────
echo [1/4] Installing PyInstaller ...
pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] pip install pyinstaller failed.
    pause
    exit /b 1
)

:: ── Install project dependencies (in case they are missing) ──────────────────
echo [2/4] Installing project dependencies ...
pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install -r requirements.txt failed.
    pause
    exit /b 1
)

:: ── Run PyInstaller ───────────────────────────────────────────────────────────
echo [3/4] Building NetStock.exe (this may take a minute) ...
pyinstaller --clean --noconfirm netstock.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. Check the output above for details.
    pause
    exit /b 1
)

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo [4/4] Build complete!
echo.
echo  Output:  dist\NetStock.exe
echo.
echo  To run:  double-click dist\NetStock.exe
echo           (netstock.db will be created next to the EXE on first launch)
echo.
echo ============================================================
pause
