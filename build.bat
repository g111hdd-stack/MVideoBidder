@echo off
setlocal ENABLEDELAYEDEXPANSION

call .venv\Scripts\activate.bat

if not defined VIRTUAL_ENV (
    echo Ошибка: виртуальное окружение не активировано.
    exit /b 1
)

python -m PyInstaller --noconfirm --clean my.spec
if errorlevel 1 (
    echo Сборка завершилась с ошибкой.
    goto :end
)

set "DIST=dist"
set "APPDIR="

for /d %%D in ("%DIST%\ProxyBrowser*") do (
    set "APPDIR=%%~fD"
    goto :found_app
)

echo Не найдена папка приложения в dist\ProxyBrowser*.
goto :end

:found_app
echo Найдена папка приложения: "%APPDIR%"

set "INTERNAL=%APPDIR%\_internal"
set "SRC=%INTERNAL%\browser"
set "DST=%APPDIR%\browser"

if not exist "%SRC%" (
    echo Перенос browser не требуется.
    goto :success
)

if exist "%DST%" (
    echo Папка "%DST%" уже существует, пропускаю перенос.
    goto :success
)

echo Переношу "%SRC%" -> "%DST%"
xcopy "%SRC%" "%DST%\" /E /I /Y
if errorlevel 1 (
    echo Ошибка при копировании папки browser.
    goto :end
)

rmdir /S /Q "%SRC%"

:success
echo Готово.

:end
pause
endlocal
