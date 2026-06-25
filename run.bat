@echo off
title NexusAI: Smart Inventory Engine
echo =========================================================
echo  Starting NexusAI: Smart Inventory Engine...
echo  Environment: Virtual Env (venv)
echo  Database: Neon Serverless PostgreSQL (Cloud)
echo  Address: http://127.0.0.1:8000
echo =========================================================
echo.

cd /d "%~dp0"
call .\venv\Scripts\activate.bat
.\venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000

pause
