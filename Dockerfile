FROM python:3.11-slim

# 1. Instalamos todo (incluído libimage-magick-perl que ayuda con los permisos)
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    imagemagick \
    potrace \
    libmagickwand-dev \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. ELIMINAR TODAS LAS RESTRICCIONES DE SEGURIDAD
# Esto permite que Ghostscript y ImageMagick trabajen sin bloquearse
RUN rm /etc/ImageMagick-6/policy.xml || true
RUN sed -i 's/SAFER/NOSAFER/g' /usr/bin/pstoedit || true

# 3. Configuración de entorno para Ghostscript
ENV GS_OPTIONS="-dNOSAFER"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 4. Asegurar carpetas y permisos totales
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input && \
    chmod -R 777 /app/static/uploads /app/data

# Exponer el puerto
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
