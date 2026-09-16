@echo off
REM Build ban one-folder + nen zip vao thu muc release\
cd /d "%~dp0"
setlocal

echo [1/4] Tao icon...
python tools\make_icon.py || goto :error

echo [2/4] Chay test...
python -m pytest -q tests || goto :error

echo [3/4] Build PyInstaller...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
python -m PyInstaller --noconfirm BestsellerCrawler.spec || goto :error

echo [4/4] Nen zip...
python tools\make_zip.py || goto :error

echo.
echo Xong.
goto :eof

:error
echo.
echo BUILD LOI
exit /b 1
