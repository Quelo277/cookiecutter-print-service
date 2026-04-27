# ============================================================
# CookieCutterPrintService - Dockerfile CORREGIDO v2
# Fix: OpenSCAD vía apt OBS (sin AppImage/FUSE)
# Fix: alias openscad-nightly correcto
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
    # Libs para OpenSCAD (apt, no AppImage - no necesita FUSE)
    libglu1-mesa \
    libopengl0 \
    libglx0 \
    libgl1 \
    # Xvfb para simular GUI headless
    xvfb \
    # Python
    python3.11 \
    python3.11-venv \
    python3-pip \
    # ImageMagick
    imagemagick \
    # Potrace (vectorización)
    potrace \
    # pstoedit (backup EPS→DXF)
    pstoedit \
    && rm -rf /var/lib/apt/lists/*

####################
# 📥 Install Tools #
####################
# Inkscape PPA
RUN add-apt-repository ppa:inkscape.dev/stable && \
    apt-get update && \
    apt-get install -y inkscape && \
    rm -rf /var/lib/apt/lists/*

# OpenSCAD nightly via OBS apt repository (Ubuntu 22.04)
# CORREGIDO: usa apt en lugar de AppImage para evitar dependencia de FUSE en Docker
# El paquete apt incluye soporte SVG nativo y fast-csg igual que el nightly
RUN wget -qO /etc/apt/trusted.gpg.d/obs-openscad-nightly.asc \
        https://files.openscad.org/OBS-Repository-Key.pub && \
    echo "deb https://download.opensuse.org/repositories/home:/t-paul/xUbuntu_22.04/ ./" \
        > /etc/apt/sources.list.d/openscad.list && \
    apt-get update && \
    apt-get install -y openscad-nightly && \
    rm -rf /var/lib/apt/lists/*

# Symlinks para que el código y el PATH encuentren openscad-nightly y openscad
RUN ln -sf /usr/bin/openscad-nightly /usr/local/bin/openscad-nightly && \
    ln -sf /usr/bin/openscad-nightly /usr/local/bin/openscad

###############
# Set workdir #
###############
WORKDIR /app

################
# 🖥️ Setup GUI #
################
RUN echo '#!/bin/sh\nXvfb :5 -screen 0 800x600x24 -nolisten tcp &\nsleep 2\nexec "$@"' \
    > /usr/local/bin/with-xvfb && chmod +x /usr/local/bin/with-xvfb

###############################
# 📦 Python dependencies      #
###############################
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

###############################
# 📂 Copy application files   #
###############################
COPY . .

# Directorios de salida
RUN mkdir -p /app/frontend/static/uploads/stl \
    /app/frontend/static/uploads/previews \
    /app/frontend/static/uploads/images \
    /app/db

EXPOSE 8000

CMD ["sh", "-c", "Xvfb :5 -screen 0 800x600x24 -nolisten tcp & sleep 2 && python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
