#!/bin/bash
# ============================================================
# CookieCutterPrintService - Script de inicio rapido
# Para desarrollo local (sin Docker)
# ============================================================

echo "=========================================="
echo "  CookieCutterPrintService - Dev Mode"
echo "=========================================="

# Verificar dependencias de sistema
echo "[1/4] Verificando dependencias de sistema..."
for tool in openscad convert potrace pstoedit; do
    if command -v $tool &> /dev/null; then
        echo "  OK: $tool"
    else
        echo "  FALTA: $tool"
        echo "  Instala las dependencias:"
        echo "    Ubuntu/Debian: sudo apt-get install openscad imagemagick potrace pstoedit"
        echo "    macOS: brew install openscad imagemagick potrace pstoedit"
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

# Inicializar base de datos
echo "[4/4] Inicializando base de datos..."
mkdir -p db frontend/static/uploads/stl frontend/static/uploads/previews

# Copiar .env si no existe
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  Creado .env desde .env.example (editalo con tus valores)"
fi

# Iniciar servidor
echo "=========================================="
echo "  Iniciando servidor en http://localhost:8000"
echo "  Admin: http://localhost:8000/admin"
echo "  Health: http://localhost:8000/health"
echo "=========================================="
python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
