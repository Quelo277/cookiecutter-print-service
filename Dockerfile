FROM python:3.11-slim

# Instalar dependencias del sistema (Capa de S.O.)
RUN apt-get update && apt-get install -y \
    inkscape \
    imagemagick \
    potrace \
    openscad \
    libglu1-mesa \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requerimientos e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Crear directorios necesarios para la app
RUN mkdir -p /app/static/uploads/stl /app/static/uploads/previews /app/static/uploads/images

# Puerto de FastAPI
EXPOSE 8000

# Comando para arrancar
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
