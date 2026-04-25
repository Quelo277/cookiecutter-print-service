# 1. Usamos una base de Python 3.11
FROM python:3.11-slim

# 2. Instalamos las herramientas de "taller" (OpenSCAD, Ghostscript y pstoedit)
# Estas son las que convierten tu imagen en un objeto 3D
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Permisos especiales para Ghostscript (necesario para evitar el error que veías)
RUN sed -i 's/rights="none" pattern="PS"/rights="read|write" pattern="PS"/' /etc/ImageMagick-6/policy.xml || true

# 4. Configuración del directorio de trabajo
WORKDIR /app

# 5. Instalamos las librerías de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiamos todo tu código al contenedor
COPY . .

# 7. Creamos las carpetas necesarias para que no den error de "permiso denegado"
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input

# 8. Comando de inicio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
