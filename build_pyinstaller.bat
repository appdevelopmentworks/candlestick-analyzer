@echo off
setlocal enabledelayedexpansion

rem Change to the repo root (location of this script)
pushd "%~dp0"

rem Disable timestamp rewriting to avoid OSError 22 on some Windows setups
set PYINSTALLER_NO_BUILD_TIMESTAMP=1

rem Ensure build directories exist/are clean
if not exist build mkdir build
if exist build\dist rmdir /s /q build\dist
if exist build\pyinstaller_tmp rmdir /s /q build\pyinstaller_tmp
if exist candlestick-analyzer.spec del /f /q candlestick-analyzer.spec

rem Ensure no stale EXE is locking the path
if exist build\dist\candlestick-analyzer.exe del /f /q build\dist\candlestick-analyzer.exe >nul 2>&1

echo [INFO] Building Windows executable via PyInstaller...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name candlestick-analyzer ^
  --icon Appimg.ico ^
  --paths src ^
  --exclude-module PyQt5 ^
  --workpath build\pyinstaller_tmp ^
  --distpath build\dist ^
  --add-data "resources;resources" ^
  --add-data "samples;samples" ^
  --add-data "config.yaml;." ^
  --add-data "schema.sql;." ^
  --add-data "Appimg.ico;." ^
  src/app.py

if %ERRORLEVEL% neq 0 (
  echo [ERROR] PyInstaller build failed.
  popd
  exit /b %ERRORLEVEL%
)

echo [INFO] Build complete. Executable located at build\dist\candlestick-analyzer.exe

popd
endlocal
