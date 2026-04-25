# 1. Usamos Python 3.11
FROM python:3.11-slim

# 2. Instalamos herramientas de imagen y 3D
# Añadimos imagemagick para solucionar el error de 'convert'
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    imagemagick \
    libmagickwand-dev \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. CRÍTICO: Permitir que ImageMagick y Ghostscript procesen archivos
# Por defecto vienen bloqueados en Linux por seguridad
RUN sed -i 's/rights="none" pattern="PS"/rights="read|write" pattern="PS"/' /etc/ImageMagick-6/policy.xml || true
RUN sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml || true
RUN sed -i 's/rights="none" pattern="EPS"/rights="read|write" pattern="EPS"/' /etc/ImageMagick-6/policy.xml || true

WORKDIR /app

# 4. Dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Código y carpetas
COPY . .
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input

# 6. Comando de inicio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
