@echo off
rem Restore the snapshot this file sits in: restore.bat <into dir> [pg port] [api port] [--no-start]
rem Unpacks the conda environment, then runs restore.py with it. See restore.py.
rem A SHORT <into> (e.g. C:\assy_restore): the environment holds paths past Windows' 260-character limit.
setlocal
set SNAP=%~dp0
set INTO=%~1
if "%INTO%"=="" (echo usage: restore.bat ^<into dir^> [pg port] [api port] [--no-start] & exit /b 2)
set PGPORT_=%~2
if "%PGPORT_%"=="" set PGPORT_=5432
set APIPORT_=%~3
if "%APIPORT_%"=="" set APIPORT_=8080
if exist "%INTO%" (echo %INTO% exists - restore into a new directory & exit /b 2)
mkdir "%INTO%\env" || exit /b 1
echo [restore] unpacking the environment
tar -xzf "%SNAP%env.tar.gz" -C "%INTO%\env" || goto :long
"%INTO%\env\Scripts\conda-unpack.exe" || goto :long
"%INTO%\env\python.exe" "%SNAP%restore.py" --snapshot "%SNAP%." --into "%INTO%" --pg-port %PGPORT_% --api-port %APIPORT_% %4
exit /b %ERRORLEVEL%
:long
echo [restore] the environment did not unpack - restore into a shorter path (e.g. C:\assy_restore): Windows refuses paths past 260 characters
exit /b 1
