FROM python:3.11-slim

# 1. Instalación de dependencias
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    imagemagick \
    potrace \
    libmagickwand-dev \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. ATAQUE A LA SEGURIDAD (Adaptado a ImageMagick 7 y Ghostscript 10)
# Creamos el directorio de la política por si no existe y escribimos la versión abierta
RUN mkdir -p /etc/ImageMagick-7 && \
    echo '<?xml version="1.0" encoding="UTF-8"?><policymap><policy domain="coder" rights="read|write" pattern="{PS,EPS,PDF,XPS}" /></policymap>' > /etc/ImageMagick-7/policy.xml

# Enlace simbólico por si el sistema busca la versión 6
RUN ln -s /etc/ImageMagick-7 /etc/ImageMagick-6 || true

# 3. EL "MARTILLAZO" A GHOSTSCRIPT
# Forzamos a Ghostscript a ignorar el modo SAFER mediante variables globales de entorno
ENV GS_OPTIONS="-dNOSAFER"
ENV G_PSTOTEXT_OPTIONS="-nosfer"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 4. Permisos de carpetas
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input && \
    chmod -R 777 /app/static/uploads /app/data /tmp

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
