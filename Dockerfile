# Usamos Python 3.11
FROM python:3.11-slim

# Instalamos dependencias del sistema para procesamiento de imágenes y 3D
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# Configuración de seguridad de Ghostscript (necesaria para pstoedit)
RUN sed -i 's/policy domain="coder" rights="none" pattern="PDF"/policy domain="coder" rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml || true

WORKDIR /app

# Copiamos y instalamos dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código
COPY . .

# Comando para iniciar la app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
