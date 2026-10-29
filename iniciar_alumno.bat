@echo off
title Tracker de Clase - Asistente del Alumno
chcp 65001 > nul
pushd "%~dp0"

echo =================================================================
echo   TALLER DE GIT Y GITHUB - PREPARACION DEL ALUMNO
echo =================================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python no esta detectado en el PATH del sistema.
    echo [*] Intentando instalar Python 3.12 automaticamente via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo [*] Instalacion completada. Por favor, cierra esta ventana y vuelve
    echo     a hacer doble clic en este archivo para continuar.
    pause
    exit /b 1
)

set "ENLACES=enlaces.md"
if exist "enlaces.local.md" set "ENLACES=enlaces.local.md"

echo [*] Abriendo enlaces desde %ENLACES%...
for /f "usebackq tokens=1 eol=#" %%L in ("%ENLACES%") do (
    echo %%L | findstr /r /b /c:"http://" /c:"https://" >nul
    if not errorlevel 1 start "" "%%L"
)

echo [*] Verificando dependencias del tracker...
pip install -r client/requirements.txt --disable-pip-version-check

echo.
echo [*] Iniciando conexion con el docente...
python client/let_track.py %*

pause
