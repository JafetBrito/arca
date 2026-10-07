@echo off
rem Compila dist\Arca.exe (un solo archivo, con ventana). Solo necesita Python 3.10+.
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Necesitas Python 3.10 o superior: https://www.python.org/downloads/ & goto :error)

echo [1/3] Instalando PyInstaller...
python -m pip install --quiet --upgrade pyinstaller || goto :error

echo [2/3] Preparando icono...
if not exist recursos\arca.ico (
  python -m pip install --quiet pillow || goto :error
  python herramientas\crear_icono.py || goto :error
)

echo [3/3] Compilando Arca.exe (tarda 1-2 minutos)...
python -m PyInstaller --noconfirm --clean --onefile --windowed --log-level WARN ^
  --name Arca --icon "%~dp0recursos\arca.ico" --add-data "%~dp0recursos\arca.ico;recursos" ^
  --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%~dp0build" "%~dp0arca_app.py" || goto :error

echo.
echo Listo: %~dp0dist\Arca.exe
echo Haz doble clic en el para abrir Arca.
exit /b 0

:error
echo.
echo Fallo la compilacion. Revisa los mensajes de arriba.
exit /b 1
