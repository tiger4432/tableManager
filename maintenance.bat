@echo off
cd /d "%~dp0"
rem The notice page while the server is off: run it after stopping the launcher, close this window before starting it.
rem maintenance.bat "until 15:00" puts that note under "Back soon".
title assyManager maintenance page

call conda activate assy_manager
if errorlevel 1 (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" assy_manager
    if errorlevel 1 (
        call "%USERPROFILE%\anaconda3\Scripts\activate.bat" assy_manager
    )
)

python server\runtime\maintenance_page.py %*
pause
