FROM python:3.11-slim

# Instalación de dependencias del sistema
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    imagemagick \
    potrace \
    libmagickwand-dev \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# ELIMINAR TODA RESTRICCIÓN DE SEGURIDAD (Necesario para el pipeline de STL)
RUN rm /etc/ImageMagick-6/policy.xml || true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Asegurar carpetas y permisos
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input && \
    chmod -R 777 /app/static/uploads

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
