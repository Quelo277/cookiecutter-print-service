FROM python:3.11-slim

# Instalar dependencias del sistema para procesamiento de imágenes y 3D
RUN apt-get update && apt-get install -y \
    inkscape \
    imagemagick \
    potrace \
    openscad \
    libglu1-mesa \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Asegurar que existan las carpetas de salida
RUN mkdir -p /app/static/uploads/stl /app/static/uploads/previews /app/static/uploads/images

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
