# CookieCutterPrintService

Aplicacion web para convertir imagenes en cortantes de galletas STL y generar presupuestos de impresion 3D.

## Stack Tecnologico

- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: HTML/CSS/JS vanilla + Three.js (visor 3D)
- **Pipeline STL**: ImageMagick -> Potrace -> pstoedit -> OpenSCAD
- **Base de datos**: SQLite
- **Contenedor**: Docker (Ubuntu 22.04)
- **Precio**: Formula configurable via variables de entorno

## Arquitectura del Pipeline

```
Imagen JPG/PNG
    |
    v
ImageMagick (binarizacion: grayscale + threshold + negate)
    |
    v
Potrace (vectorizacion: pnm -> eps)
    |
    v
pstoedit (conversion: eps -> dxf)
    |
    v
OpenSCAD (extrusion + mango)
    |
    v
STL generado
    |
    v
numpy-stl (calculo de volumen)
    |
    v
Precio = (volumen_cm3 * costo_filamento + costo_base) * margen
```

## Estructura del Proyecto

```
cookiecutter-print-service/
├── app/                          # Backend FastAPI
│   ├── __init__.py
│   ├── main.py                   # Endpoints API + frontend routes
│   ├── config.py                 # Variables de entorno
│   ├── database.py               # SQLite operations
│   ├── stl_generator.py          # Pipeline Image->STL
│   └── notifications.py          # SMTP notifications
├── frontend/
│   ├── templates/
│   │   ├── index.html            # Pagina principal
│   │   └── admin.html            # Panel admin
│   └── static/
│       ├── css/style.css
│       ├── js/app.js
│       └── uploads/              # Imagenes y STL generados
├── openscad_templates/           # Plantillas OpenSCAD
├── db/                           # SQLite database
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## API Endpoints

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/` | Pagina principal (formulario) |
| GET | `/admin` | Panel administrativo |
| POST | `/api/upload` | Subir imagen y generar STL |
| POST | `/api/order` | Registrar pedido |
| GET | `/api/orders` | Listar pedidos |
| GET | `/api/orders/{id}` | Detalle de pedido |
| PATCH | `/api/orders/{id}/status` | Cambiar estado |
| GET | `/api/stats` | Estadisticas |
| GET | `/api/download/{filename}` | Descargar STL |
| GET | `/api/stl-preview/{job_id}` | Datos STL para Three.js |
| GET | `/health` | Health check |

## Variables de Entorno

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `HOST` | 0.0.0.0 | Host del servidor |
| `PORT` | 8000 | Puerto |
| `CURRENCY` | ARS | Moneda |
| `CURRENCY_SYMBOL` | $ | Simbolo monetario |
| `COSTO_FILAMENTO_POR_CM3` | 0.5 | Costo del filamento por cm3 |
| `COSTO_BASE` | 300.0 | Costo fijo base |
| `MARGEN` | 1.4 | Multiplicador de margen |
| `WALL_HEIGHT` | 15 | Altura pared del cortante (mm) |
| `WALL_THICKNESS` | 1.2 | Grosor de la pared (mm) |
| `HANDLE_HEIGHT` | 8 | Altura del mango (mm) |
| `HANDLE_THICKNESS` | 3 | Grosor del mango (mm) |
| `SMTP_HOST` | (vacío) | Servidor SMTP |
| `SMTP_PORT` | 587 | Puerto SMTP |
| `SMTP_USER` | (vacío) | Usuario SMTP |
| `SMTP_PASS` | (vacío) | Password SMTP |
| `SMTP_TO` | admin@... | Email destino notificaciones |

## Despliegue en EasyPanel (Paso a Paso)

### Opcion 1: Docker Compose (Recomendado)

1. **Crear proyecto en EasyPanel**:
   - En EasyPanel, ir a "Services" -> "Add Service"
   - Seleccionar "Docker Compose"
   - Nombre: `cookiecutter-print-service`

2. **Subir archivos**:
   - Subir el archivo `docker-compose.yml` y el `Dockerfile`
   - O conectar repositorio Git

3. **Configurar variables de entorno**:
   - En la seccion "Environment", agregar las variables:
   ```
   CURRENCY=ARS
   CURRENCY_SYMBOL=$
   COSTO_FILAMENTO_POR_CM3=0.5
   COSTO_BASE=300.0
   MARGEN=1.4
   SMTP_HOST=smtp.gmail.com      # opcional
   SMTP_USER=tu-email@gmail.com   # opcional
   SMTP_PASS=tu-app-password      # opcional
   SMTP_TO=admin@tudominio.com    # opcional
   PUBLIC_URL=https://tudominio.com  # URL de EasyPanel
   ```

4. **Exponer puerto**:
   - EasyPanel detecta automaticamente el puerto 8000
   - O configurar manualmente el mapping: `8000:8000`

5. **Deploy**:
   - Click en "Deploy"
   - EasyPanel ejecuta `docker-compose up -d`
   - Verificar logs en "Logs" tab

### Opcion 2: Dockerfile Directo

1. En EasyPanel: "Services" -> "Add Service" -> "Dockerfile"
2. Subir o conectar el repositorio
3. EasyPanel detecta el Dockerfile automaticamente
4. Configurar environment variables
5. Deploy

### Opcion 3: CLI (VPS propio)

```bash
# 1. Clonar repositorio
git clone <repo-url> cookiecutter-print-service
cd cookiecutter-print-service

# 2. Configurar variables
cp .env.example .env
# Editar .env con tus valores

# 3. Deploy con Docker Compose
docker-compose up -d --build

# 4. Verificar
docker-compose logs -f
curl http://localhost:8000/health
```

## Como Usar

1. **Subir imagen**: Arrastra o selecciona una imagen JPG/PNG con fondo contrastante
2. **Parametros opcionales**: Expandir "Parametros avanzados" para ajustar altura/grosor
3. **Generar**: Click en "Generar cortante y presupuesto"
4. **Preview 3D**: El modelo STL se muestra en el visor Three.js interactivo
5. **Precio**: Se calcula automaticamente segun la formula configurada
6. **Descargar**: Podes descargar el STL gratis para imprimirlo vos mismo
7. **Pedido**: Completa tus datos y confirma el pedido de impresion

## Panel Admin

Acceder a `/admin` para ver:
- Estadisticas de pedidos
- Listado completo con filtros por estado
- Cambio de estado (pendiente -> en_proceso -> completado)

## Troubleshooting

### OpenSCAD no genera STL
- Verificar que la imagen tiene buen contraste
- Revisar logs: `docker-compose logs -f`
- Probar con una imagen mas simple (silueta definida)

### Error "Herramientas faltantes"
- El Dockerfile instala todo automaticamente
- Si falla, ejecutar manualmente en el contenedor:
  ```bash
  docker exec -it cookiecutter-print-service bash
  openscad --version
  potrace --version
  convert --version
  ```

### Puerto no responde
- Verificar que no hay conflicto de puertos
- Cambiar el mapping en docker-compose.yml: `"8080:8000"`

## Licencia

MIT - Libre para uso personal y comercial.
