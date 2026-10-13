@echo off
rem Double-click to run QR Attendance on this computer (no Docker needed).
cd /d "%~dp0\.."
if not exist "data\attendance.db" if "%ATT_ADMIN_PASSWORD%"=="" set /p ATT_ADMIN_PASSWORD=First start: choose a password for the "admin" account:
echo.
echo Keep this window open while you use the system. The three portals:
echo   Students:  http://localhost:8000/student
echo   Teachers:  http://localhost:8000/teacher
echo   Admin:     http://localhost:8000/admin
echo Forgot-password codes for teachers and admin appear in this window when email is not set up.
echo.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
