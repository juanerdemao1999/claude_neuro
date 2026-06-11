@echo off
setlocal
set QT_API=PySide6

if not exist license_public_key.pem (
  echo Missing license_public_key.pem.
  echo Run: py -3.12 tools\license_generator_app.py
  echo The key generator creates the public key used by packaged customer builds.
  exit /b 1
)

pyinstaller --noconfirm --clean NEX5SpikeLFPAnalyzer.spec

echo.
echo Build finished. EXE is in dist\NEX5SpikeLFPAnalyzer\
endlocal
