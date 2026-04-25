FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    pstoedit \
    ghostscript \
    openscad \
    imagemagick \
    potrace \
    libmagickwand-dev \
    libgl1-mesa-dev \
    libplot-dev \
    && rm -rf /var/lib/apt/lists/*

# Abrimos las políticas de ImageMagick 7
RUN mkdir -p /etc/ImageMagick-7 && \
    echo '<?xml version="1.0" encoding="UTF-8"?><policymap><policy domain="coder" rights="read|write" pattern="{PS,EPS,PDF,XPS}" /></policymap>' > /etc/ImageMagick-7/policy.xml

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/static/uploads/previews /app/static/uploads/stl /app/static/uploads/input && \
    chmod -R 777 /app/static/uploads /app/data /tmp

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
