@echo off
rem Atajo de consola: "arca respaldar ...", "arca estado", "arca dice hola"...
rem Sin argumentos abre la ventana grafica (no hace falta compilar el .exe).
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
where python >nul 2>nul || (echo Necesitas Python 3.10 o superior: https://www.python.org/downloads/ & exit /b 1)
python "%~dp0arca_app.py" %*
