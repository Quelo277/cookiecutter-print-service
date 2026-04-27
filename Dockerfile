# ============================================================
# CookieCutterPrintService - Dockerfile CORREGIDO
# Basado en Papooch/cookie-cutter-generator
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
    software-properties-common \
    # Libs needed for OpenSCAD AppImage
    libfuse2 \
    libopengl0 \
    libglx0 \
    libgl1 \
    libegl1-mesa \
    # Xvfb needed to simulate GUI for headless OpenSCAD and Inkscape
    xvfb \
    # Python
    python3.11 \
    python3.11-venv \
    python3-pip \
    # ImageMagick (for initial image processing)
    imagemagick \
    # Potrace (for vectorization)
    potrace \
    # pstoedit (backup for EPS->DXF if needed)
    pstoedit \
    && rm -rf /var/lib/apt/lists/*

####################
# 📥 Install Tools #
####################
# Register inkscape repositories and install
RUN add-apt-repository ppa:inkscape.dev/stable && \
    apt-get update && \
    apt-get install -y inkscape && \
    rm -rf /var/lib/apt/lists/*

# Download OpenSCAD nightly AppImage (same as reference)
# The nightly version contains SVG import support and fast-csg performance boost
RUN wget -O /usr/local/bin/openscad-nightly \
    --progress=bar:force \
    https://files.openscad.org/snapshots/OpenSCAD-2024.12.04.ai21522-x86_64.AppImage && \
    chmod a+x /usr/local/bin/openscad-nightly

# Alias openscad → openscad-nightly for compatibility
RUN ln -sf /usr/local/bin/openscad-nightly /usr/local/bin/openscad

###############
# Set workdir #
###############
WORKDIR /app

################
# 🖥️ Setup GUI #
################
# Xvfb must run for OpenSCAD headless rendering
# Source: https://forum.openscad.org/Headless-OpenSCAD-td5187.html
RUN echo '#!/bin/sh\n\
Xvfb :5 -screen 0 800x600x24 -nolisten tcp &\n\
sleep 2\n\
exec "$@"' > /usr/local/bin/with-xvfb && \
    chmod +x /usr/local/bin/with-xvfb

###############################
# 📦 Python dependencies      #
###############################
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

###############################
# 📂 Copy application files   #
###############################
COPY . .

# Ensure output directories exist
RUN mkdir -p /app/frontend/static/uploads/stl \
    /app/frontend/static/uploads/previews \
    /app/frontend/static/uploads/images \
    /app/db

EXPOSE 8000

# Start Xvfb in background, then uvicorn
CMD ["sh", "-c", "Xvfb :5 -screen 0 800x600x24 -nolisten tcp & sleep 2 && python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
