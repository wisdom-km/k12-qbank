@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1
if defined K12_PYTHON goto use_env
where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 goto use_conda
where py >nul 2>&1
if !ERRORLEVEL! EQU 0 goto use_py
echo Python 3.12 was not found. Install conda env k12-qbank or set K12_PYTHON. See issue 88.
exit /b 1

:use_env
"%K12_PYTHON%" "%~dp0import_book.py" %*
set "RC=!ERRORLEVEL!"
goto after

:use_conda
conda run -n k12-qbank python "%~dp0import_book.py" %*
set "RC=!ERRORLEVEL!"
goto after

:use_py
py -3.12 "%~dp0import_book.py" %*
set "RC=!ERRORLEVEL!"
goto after

:after
if "%~1"=="" pause
exit /b !RC!
