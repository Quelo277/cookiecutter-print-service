FROM python:3.11-slim

# 1. Instalamos las herramientas esenciales
# Agregamos potrace y eliminamos pstoedit si quieres para limpiar
RUN apt-get update && apt-get install -y \
    potrace \
    openscad \
    imagemagick \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Configuración de ImageMagick 7 (por si lo usas para redimensionar)
RUN mkdir -p /etc/ImageMagick-7 && \
    echo '<?xml version="1.0" encoding="UTF-8"?><policymap><policy domain="coder" rights="read|write" pattern="{PNG,JPEG,JPG,BMP}" /></policymap>' > /etc/ImageMagick-7/policy.xml

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 3. Permisos de carpetas
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input && \
    chmod -R 777 /app/static/uploads /app/data /tmp

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
