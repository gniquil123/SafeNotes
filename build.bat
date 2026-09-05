@echo off
setlocal
rem Build SafeNotes into a single exe: dist\SafeNotes.exe
rem Typical build time: 2-4 minutes. Some steps are SILENT for 1-2 minutes
rem (scanning Qt DLLs and compressing the exe) - that is normal, do not close.

cd /d "%~dp0"

rem Clear foreign PYTHONPATH so PyInstaller does not scan unrelated projects
set PYTHONPATH=

pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo pyinstaller not found, installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install pyinstaller. Check network / pip.
        pause
        exit /b 1
    )
)

echo Step 1/3: analyzing and collecting... (silent phases are normal)
python -m PyInstaller --noconfirm --noconsole --onefile --name SafeNotes ^
  --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  --hidden-import argon2.low_level ^
  --exclude-module cryptography.x509 --exclude-module cryptography.openssl ^
  --exclude-module cryptography.hazmat.primitives.serialization.ssh ^
  --exclude-module tkinter --exclude-module pygame --exclude-module numpy ^
  --exclude-module matplotlib --exclude-module pandas --exclude-module scipy ^
  --exclude-module PIL --exclude-module PyQt5 --exclude-module PyQt6 ^
  --exclude-module PySide2 --exclude-module hermes_agent ^
  main.py
if errorlevel 1 (
    echo.
    echo Build FAILED. See messages above.
    pause
    exit /b 1
)

echo Step 2/3: self-test the packaged exe... (takes ~10s, no window shown)
set QT_QPA_PLATFORM=offscreen
set SAFENOTES_LOW_KDF=1
dist\SafeNotes.exe --smoke
if errorlevel 1 (
    echo.
    echo WARNING: build succeeded but self-test FAILED. Please verify manually.
    pause
    exit /b 1
)
set QT_QPA_PLATFORM=
set SAFENOTES_LOW_KDF=

echo Step 3/3: done.
echo.
echo Build OK: dist\SafeNotes.exe  (rename to any Chinese name you like)
pause
