FROM python:3.11-slim

# 1. Instalamos todas las dependencias
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    imagemagick \
    potrace \
    libmagickwand-dev \
    libgl1-mesa-dev \
    # Esta librería ayuda a pstoedit con los formatos vectoriales
    libploticus0 \ 
    && rm -rf /var/lib/apt/lists/*

# 2. ELIMINAR RESTRICCIONES Y FORZAR PERMISOS
# Eliminamos la política de ImageMagick
RUN rm /etc/ImageMagick-6/policy.xml || true

# Modificamos la configuración global de Ghostscript para que acepte todo
RUN sed -i 's/read-only/read-write/g' /usr/share/ghostscript/*/Resource/Init/gs_init.ps || true

WORKDIR /app

# 3. Variables de entorno para saltar la seguridad de Ghostscript
ENV GS_OPTIONS="-dNOSAFER -dALLOWPSTRANSPARENCY"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 4. Carpetas con permisos totales (777)
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input && \
    chmod -R 777 /app/static/uploads /app/data /tmp

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
