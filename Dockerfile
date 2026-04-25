# ============================================================
# CookieCutterPrintService - Dockerfile
# Contenedor unico con: Ubuntu, OpenSCAD, ImageMagick, Potrace,
# Python 3.11+ y la aplicacion FastAPI.
# ============================================================

FROM ubuntu:22.04

# Evitar prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- 1. Dependencias de sistema ---
RUN apt-get update && apt-get install -y \
    # Python 3.11 y pip
    python3.11 \
    python3.11-venv \
    python3-pip \
    # ImageMagick
    imagemagick \
    # Potrace (vectorizacion)
    potrace \
    # pstoedit (EPS -> DXF)
    pstoedit \
    # OpenSCAD
    openscad \
    # Herramientas utiles
    curl \
    wget \
    git \
    ca-certificates \
    # Limpieza
    && rm -rf /var/lib/apt/lists/*

# Verificar instalaciones
RUN echo "=== Versiones instaladas ===" \
    && python3.11 --version \
    && convert --version | head -1 \
    && potrace --version | head -1 \
    && pstoedit -help | head -1 \
    && openscad --version | head -1

# --- 2. Directorio de trabajo ---
WORKDIR /app

# --- 3. Copiar dependencias Python ---
COPY requirements.txt .

# Instalar dependencias Python
RUN pip3 install --no-cache-dir -r requirements.txt

# --- 4. Copiar codigo fuente ---
COPY . .

# Crear directorios necesarios
RUN mkdir -p db frontend/static/uploads/stl frontend/static/uploads/previews

# --- 5. Puerto y healthcheck ---
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# --- 6. Comando de inicio ---
CMD ["python3.11", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
