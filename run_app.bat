@echo off
cd /d "%~dp0"

echo [Launcher] Activating conda environment 'assy_manager'...
call conda activate assy_manager
if errorlevel 1 (
    echo [Launcher] Failed to activate environment via 'conda activate'. Trying direct miniconda path...
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" assy_manager
    if errorlevel 1 (
        echo [Launcher] Trying direct anaconda path...
        call "%USERPROFILE%\anaconda3\Scripts\activate.bat" assy_manager
    )
)

echo [Launcher] Invoking run_decoupled_app.py ...
python run_decoupled_app.py
pause
