# ============================================================
# CookieCutterPrintService - Dockerfile CORREGIDO v4
# Fix: Instalación limpia de Python 3.11 y Uvicorn
# ============================================================

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:5

###################
# 📥 Install Libs #
###################
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    software-properties-common \
    libglu1-mesa \
    libopengl0 \
    libglx0 \
    libgl1 \
    xvfb \
    python3.11 \
    python3.11-dev \
    python3-pip \
    imagemagick \
    potrace \
    pstoedit \
    && rm -rf /var/lib/apt/lists/*

# Forzar que pip se instale correctamente para Python 3.11
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

####################
# 📥 Install Tools #
####################
# Inkscape PPA
RUN add-apt-repository ppa:inkscape.dev/stable && \
    apt-get update && \
    apt-get install -y inkscape && \
    rm -rf /var/lib/apt/lists/*

# OpenSCAD nightly via OBS
RUN wget -qO /etc/apt/trusted.gpg.d/obs-openscad-nightly.asc \
        https://files.openscad.org/OBS-Repository-Key.pub && \
    echo "deb https://download.opensuse.org/repositories/home:/t-paul/xUbuntu_22.04/ ./" \
        > /etc/apt/sources.list.d/openscad.list && \
    apt-get update && \
    apt-get install -y openscad-nightly && \
    rm -rf /var/lib/apt/lists/*

# Symlinks
RUN ln -sf /usr/bin/openscad-nightly /usr/local/bin/openscad-nightly && \
    ln -sf /usr/bin/openscad-nightly /usr/local/bin/openscad

WORKDIR /app

###############################
# 📦 Python dependencies      #
###############################
COPY requirements.txt .
# Instalamos los módulos usando el binario de python3.11 directamente
RUN python3.11 -m pip install --no-cache-dir -r requirements.txt

###############################
# 📂 Copy application files   #
###############################
COPY . .

# Directorios de salida con permisos para evitar errores de escritura
RUN mkdir -p /app/frontend/static/uploads/stl \
    /app/frontend/static/uploads/previews \
    /app/frontend/static/uploads/images \
    /app/db && \
    chmod -R 777 /app/frontend/static/uploads

EXPOSE 8000

# CMD: Arrancamos Xvfb y luego el módulo uvicorn con python3.11
CMD ["sh", "-c", "Xvfb :5 -screen 0 800x600x24 -nolisten tcp & sleep 5 && python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
