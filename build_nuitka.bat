@echo off
setlocal enabledelayedexpansion

rem Change directory to repository root
pushd "%~dp0"

if not exist build mkdir build
if exist build\nuitka rmdir /s /q build\nuitka

echo [INFO] Building Windows executable via Nuitka...
python -m nuitka ^
  --onefile ^
  --enable-plugin=pyside6 ^
  --follow-imports ^
  --include-data-dir=resources=resources ^
  --include-data-dir=samples=samples ^
  --include-data-file=config.yaml=config.yaml ^
  --include-data-file=schema.sql=schema.sql ^
  --include-data-file=Appimg.ico=Appimg.ico ^
  --windows-icon-from-ico=Appimg.ico ^
  --windows-company-name="YourCompany" ^
  --windows-product-name="Candlestick Analyzer" ^
  --windows-file-version=1.0.0 ^
  --output-dir=build\nuitka ^
  src/app.py

if %ERRORLEVEL% neq 0 (
  echo [ERROR] Nuitka build failed.
  popd
  exit /b %ERRORLEVEL%
)

echo [INFO] Build complete. Executable located under build\nuitka

popd
endlocal
