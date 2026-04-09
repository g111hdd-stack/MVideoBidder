@echo off
setlocal ENABLEDELAYEDEXPANSION

call .venv\Scripts\activate

if not defined VIRTUAL_ENV (
    echo Ошибка: виртуальное окружение не активировано.
    exit /b 1
)

pyinstaller --noconfirm --clean my.spec
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

echo Не найдена папка приложения в dist\ProxyBrowser_*.
goto :end

:found_app
echo Найдена папка приложения: "%APPDIR%"

set "INTERNAL=%APPDIR%\_internal"
set "SRC=%INTERNAL%\browser"
set "DST=%APPDIR%\browser"

if not exist "%SRC%" (
    echo Источник для переноса не найден: "%SRC%"
    goto :end
)

if exist "%DST%" (
    echo Папка "%DST%" уже существует, пропускаю перенос.
) else (
    echo Переношу "%SRC%" -> "%DST%"
    xcopy "%SRC%" "%DST%\" /E /I /Y
    if errorlevel 1 (
        echo Ошибка при копировании папки browser.
        goto :end
    )
    rmdir /S /Q "%SRC%"
)

echo Готово.

:end
deactivate
pause
endlocal
