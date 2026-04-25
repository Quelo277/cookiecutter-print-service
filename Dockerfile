FROM python:3.11-slim

# 1. Instalamos dependencias incluyendo 'libgs-dev' y herramientas de compilación
RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    imagemagick \
    potrace \
    libmagickwand-dev \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. ATAQUE DIRECTO A LA SEGURIDAD DE GHOSTSCRIPT
# Sobreescribimos la política de seguridad para que sea totalmente abierta
RUN echo '<?xml version="1.0" encoding="UTF-8"?><policymap><policy domain="coder" rights="read|write" pattern="PS" /><policy domain="coder" rights="read|write" pattern="EPS" /><policy domain="coder" rights="read|write" pattern="PDF" /><policy domain="coder" rights="read|write" pattern="XPS" /></policymap>' > /etc/ImageMagick-6/policy.xml

# 3. EL "TRUCO" PARA PSTOEDIT:
# Forzamos a que ignore el modo SAFER creando un alias o variable
ENV GS_OPTIONS="-dNOSAFER -dDEBUG"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 4. Crear carpetas y dar permisos exagerados para evitar bloqueos de /tmp
RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input && \
    chmod -R 777 /app/static/uploads /app/data /tmp

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
