@echo off
cd /d "%~dp0"
rem Applies the release bundles in release\ - the same step the launcher takes when it starts
rem (server\runtime\release_apply.py). Then restart the launcher.

call conda activate assy_manager
if errorlevel 1 (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" assy_manager
    if errorlevel 1 (
        call "%USERPROFILE%\anaconda3\Scripts\activate.bat" assy_manager
    )
)

python server\runtime\release_apply.py
pause
