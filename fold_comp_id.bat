@echo off
cd /d "%~dp0"

call conda activate assy_manager
if errorlevel 1 (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" assy_manager
    if errorlevel 1 (
        call "%USERPROFILE%\anaconda3\Scripts\activate.bat" assy_manager
    )
)

python server\scripts\fold_comp_id.py %*
pause
