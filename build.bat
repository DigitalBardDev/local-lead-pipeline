@echo off
echo Building Local Lead Hunter 2.0 Executable...
echo.

REM Set Playwright to bundle browsers inside the executable path (optional, increases size)
REM set PLAYWRIGHT_BROWSERS_PATH=0

venv\Scripts\pyinstaller.exe ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name "Local Lead Hunter" ^
    --add-data "recipes;recipes" ^
    --add-data "config.json;." ^
    run_app.py

echo.
echo Build complete! Your standalone app is in the "dist\Local Lead Hunter" folder.
echo You can zip that folder and send it to your clients.
pause
