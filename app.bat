@echo off
title Masterproef - Yves Geebelen

:menu
echo.
echo ==========================================================
echo Masterproef - Research Tool
echo ==========================================================
echo.
echo 1. Start the application
echo 2. Stop the application
echo 3. Run post-hoc classification script
echo 4. Clean / Reset (removes Docker containers, networks, and images)
echo 5. Exit
echo.
set /p choice="Choose an option (1/2/3/4/5): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto posthoc
if "%choice%"=="4" goto clean
if "%choice%"=="5" exit /b 0
echo Invalid choice. Please try again.
goto menu

:start
if exist .env goto run_app

echo.
echo ==========================================================
echo First-time Setup: Configuring .env file
echo ==========================================================
echo If you want to enable AI features, please enter your details.
echo (Or press Enter to skip and leave them blank)
echo.
set /p api_key="Enter AZURE_OPENAI_API_KEY: "
set /p endpoint="Enter AZURE_OPENAI_ENDPOINT: "
set /p groq_key="Enter GROQ_API_KEY: "
echo.

copy .env.example .env >nul 2>&1

powershell -Command "(gc .env) -replace 'AZURE_OPENAI_API_KEY=', ('AZURE_OPENAI_API_KEY=' + [char]34 + '%api_key%' + [char]34) | sc .env"
powershell -Command "(gc .env) -replace 'AZURE_OPENAI_ENDPOINT=', ('AZURE_OPENAI_ENDPOINT=' + [char]34 + '%endpoint%' + [char]34) | sc .env"
powershell -Command "(gc .env) -replace 'GROQ_API_KEY=', ('GROQ_API_KEY=' + [char]34 + '%groq_key%' + [char]34) | sc .env"

echo .env file configured successfully.
echo.

:run_app
echo.
echo Building and starting Docker containers (this may take a moment)...
echo.
docker compose build --quiet
docker compose up -d
echo.
echo SUCCESS! Opening your browser to http://localhost
echo.
timeout /t 3 /nobreak >nul
start http://localhost
goto menu

:stop
echo.
echo Stopping the application...
echo.
docker compose down
echo.
echo Successfully stopped!
goto menu

:posthoc
echo.
echo Starting post-hoc classification in Docker...
echo.
docker compose build --quiet backend
docker compose run --rm -v ./backend:/app backend python post_hoc_classification.py
goto menu

:clean
echo.
echo ==========================================================
echo Warning: This will delete Docker containers, images, and networks.
echo Your .env file and collected data in the results folder will NOT be touched.
echo ==========================================================
echo.
set /p confirm="Are you sure you want to clean? (y/n): "
if /i not "%confirm%"=="y" goto menu
echo.
echo Cleaning up application resources...
echo.
docker compose down --rmi all --volumes --remove-orphans
echo.
echo Successfully cleaned!
goto menu
