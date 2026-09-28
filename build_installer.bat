@echo off
REM Build ban one-folder + zip (build.bat) roi dong goi file cai dat Inno Setup vao release\
cd /d "%~dp0"
setlocal

call "%~dp0build.bat" || goto :error

echo [5/5] Dong goi file cai dat...
set "ISCC_PATH="
for %%I in (ISCC.exe) do set "ISCC_PATH=%%~$PATH:I"
if not defined ISCC_PATH if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH (
    echo Chua cai Inno Setup 6. Cai tu https://jrsoftware.org/isdl.php roi chay lai.
    goto :error
)

for /f "delims=" %%V in ('python -c "from app.app_version import APP_VERSION; print(APP_VERSION)"') do set "APP_VERSION=%%V"
if not defined APP_VERSION goto :error

"%ISCC_PATH%" /Q /DAppVersion=%APP_VERSION% installer\BestsellerCrawler.iss || goto :error

echo.
echo Xong: release\BestsellerCrawlerSetup-%APP_VERSION%.exe
goto :eof

:error
echo.
echo BUILD INSTALLER LOI
exit /b 1
