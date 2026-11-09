@echo off
rem Yobi setup: double-click me. Copies Yobi to your account (no admin) and adds shortcuts.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0payload\app\install.ps1" %*
if errorlevel 1 pause
