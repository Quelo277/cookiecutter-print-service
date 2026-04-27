#!/bin/bash
# ============================================================
# CookieCutterPrintService - Script de inicio rapido (dev local)
# CORREGIDO: verifica Inkscape + OpenSCAD nightly + Xvfb
# ============================================================

echo "=========================================="
echo "  CookieCutterPrintService - Dev Mode"
echo "=========================================="

# Verificar dependencias de sistema
echo "[1/4] Verificando dependencias de sistema..."
for tool in inkscape openscad-nightly convert potrace xvfb-run; do
    if command -v $tool &> /dev/null; then
        echo "  OK: $tool"
    else
        echo "  FALTA: $tool"
        echo "  Instala las dependencias:"
        echo "    Ubuntu/Debian:"
        echo "      sudo apt-get install inkscape imagemagick potrace xvfb"
        echo "      sudo apt-get install libfuse2 libopengl0 libglx0 libgl1 libegl1-mesa"
        echo "      wget -O /usr/local/bin/openscad-nightly https://files.openscad.org/snapshots/OpenSCAD-2024.12.04.ai21522-x86_64.AppImage"
        echo "      sudo chmod +x /usr/local/bin/openscad-nightly"
        echo "      sudo ln -s /usr/local/bin/openscad-nightly /usr/local/bin/openscad"
        exit 1
    fi
done

# Crear entorno virtual si no existe
echo "[2/4] Configurando entorno Python..."
if [ ! -d "venv" ]; then
    python3.11 -m venv venv
fi
source venv/bin/activate

# Instalar dependencias
echo "[3/4] Instalando dependencias Python..."
pip install -q -r requirements.txt

# Inicializar base de datos y directorios
echo "[4/4] Inicializando base de datos..."
mkdir -p db frontend/static/uploads/stl frontend/static/uploads/previews frontend/static/uploads/images

# Copiar .env si no existe
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  Creado .env desde .env.example (editalo con tus valores)"
fi

# Iniciar Xvfb en background (necesario para OpenSCAD headless)
XVFB_PID=""
if ! pgrep -x "Xvfb" > /dev/null; then
    echo "  Iniciando Xvfb..."
    Xvfb :5 -screen 0 800x600x24 -nolisten tcp &
    XVFB_PID=$!
    sleep 2
fi
export DISPLAY=:5

# Iniciar servidor
echo "=========================================="
echo "  Iniciando servidor en http://localhost:8000"
echo "  Admin: http://localhost:8000/admin"
echo "  Health: http://localhost:8000/health"
echo "=========================================="
python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Cleanup: matar Xvfb si lo iniciamos nosotros
if [ -n "$XVFB_PID" ]; then
    kill $XVFB_PID 2>/dev/null
fi
