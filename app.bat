@echo off
title Masterproef - Yves Geebelen

:menu
echo.
echo ==========================================================
echo    Masterproef - Research Tool
echo ==========================================================
echo.
echo    1. Start the application
echo    2. Stop the application
echo    3. Exit
echo.
set /p choice="   Choose an option (1/2/3): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" exit /b 0
echo    Invalid choice. Please try again.
goto menu

:start
if not exist .env (
    echo.
    echo    Warning: .env file not found!
    echo    Creating .env from .env.example with default values.
    echo    AI features will be disabled.
    echo.
    echo    To enable AI, edit .env and add your Azure OpenAI credentials.
    echo.
    copy .env.example .env >nul 2>&1
)

echo.
echo    Starting the application...
echo.
docker compose up -d --build
echo.
echo    SUCCESS! Opening your browser to http://localhost
echo.
timeout /t 3 /nobreak >nul
start http://localhost
goto menu

:stop
echo.
echo    Stopping the application...
echo.
docker compose down
echo.
echo    Successfully stopped!
goto menu
