@echo off
setlocal
cd /d "%~dp0"
set "DOCTORADO_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%DOCTORADO_PY%" (
    start "" "%DOCTORADO_PY%" "%~dp0app.py"
    exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0app.py"
    exit /b
)
where py.exe >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0app.py"
    exit /b
)
echo No se encuentra Python 3.12 o posterior.
echo La app no necesita paquetes adicionales. Instala Python desde python.org,
echo o abre esta carpeta en el equipo donde esta disponible el entorno de Codex.
pause
